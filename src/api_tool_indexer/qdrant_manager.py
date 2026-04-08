"""Qdrant manager for api_tool_collection with hybrid search support.
for the api_tool_collection used by the API Tool Calling workflow.
"""

from typing import Any, Dict, Optional
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    SparseVectorParams,
    SparseIndexParams,
    SparseVector,
    PointIdsList,
)

from api_tool_indexer.constants import ApiToolIndexerConstants
from api_tool_indexer.models import EnrichedEndpoint

# Error messages
_CLIENT_NOT_INITIALIZED = "Qdrant client not initialized"


class ApiToolQdrantManager:
    """Manages Qdrant operations for api_tool_collection with hybrid search.

    One point per endpoint is stored.
    """

    def __init__(
        self,
        host: str = ApiToolIndexerConstants.DEFAULT_QDRANT_HOST,
        port: int = ApiToolIndexerConstants.DEFAULT_QDRANT_PORT,
        collection_name: str = ApiToolIndexerConstants.COLLECTION_NAME,
    ) -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.client: Optional[QdrantClient] = None

    def connect(self) -> None:
        """Connect to Qdrant."""
        try:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}")
            self.client = QdrantClient(
                host=self.host,
                port=self.port,
                timeout=30,
                prefer_grpc=False,
                api_key=None,
            )
            logger.success("Successfully connected to Qdrant")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    def ensure_collection(self) -> None:
        """Ensure api_tool_collection exists with hybrid vector config.

        The collection uses named vectors:
        - 'dense': 3072-dim cosine similarity vectors for semantic matching
        - 'sparse': BM25-style sparse vectors for keyword matching
        """
        if not self.client:
            raise RuntimeError(_CLIENT_NOT_INITIALIZED)

        try:
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]

            if self.collection_name in collection_names:
                self._validate_existing_collection()
            else:
                self._create_collection()

        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}")
            raise

    def _validate_existing_collection(self) -> None:
        """Validate that the existing API Tool collection has correct hybrid vector config."""
        if not self.client:
            raise RuntimeError(_CLIENT_NOT_INITIALIZED)

        collection_info = self.client.get_collection(self.collection_name)
        vectors_config = collection_info.config.params.vectors

        if isinstance(vectors_config, dict):
            if ApiToolIndexerConstants.DENSE_VECTOR_NAME in vectors_config:
                existing_size = vectors_config[
                    ApiToolIndexerConstants.DENSE_VECTOR_NAME
                ].size
                if existing_size != ApiToolIndexerConstants.VECTOR_SIZE:
                    logger.error(
                        f"Collection '{self.collection_name}' has incompatible vector size: "
                        f"{existing_size} (expected {ApiToolIndexerConstants.VECTOR_SIZE})"
                    )
                    raise RuntimeError(
                        f"Collection '{self.collection_name}' has incompatible vector size: "
                        f"{existing_size} (expected {ApiToolIndexerConstants.VECTOR_SIZE}). "
                        "Delete the collection and re-index all endpoints."
                    )
                logger.info(
                    f"Collection '{self.collection_name}' already exists "
                    f"with correct hybrid vector config (dense: {existing_size}d + sparse)"
                )
            else:
                # Old collection format (unnamed/single vector) — needs migration
                logger.error(
                    f"Collection '{self.collection_name}' exists but uses old single-vector format. "
                    "Migration to named vectors (dense + sparse) required."
                )
                raise RuntimeError(
                    f"Collection '{self.collection_name}' uses old single-vector format. "
                    "Please delete the collection and re-index all endpoints. "
                    f"Delete with: qdrant.client.delete_collection('{self.collection_name}') "
                    "or via Qdrant UI/API."
                )
        elif vectors_config is not None:
            # Direct VectorParams object (old single-vector format)
            logger.error(
                f"Collection '{self.collection_name}' exists but uses old single-vector format."
            )
            raise RuntimeError(
                f"Collection '{self.collection_name}' uses old single-vector format. "
                "Please delete the collection and re-index all endpoints. "
                f"Delete with: qdrant.client.delete_collection('{self.collection_name}') "
                "or via Qdrant UI/API."
            )
        else:
            logger.error(
                f"Collection '{self.collection_name}' exists but vector config cannot be determined."
            )
            raise RuntimeError(
                f"Collection '{self.collection_name}' vector config cannot be determined. "
                "Manual intervention required."
            )

    def _create_collection(self) -> None:
        """Create api_tool_collection with hybrid vector configuration (dense + sparse)."""
        if not self.client:
            raise RuntimeError(_CLIENT_NOT_INITIALIZED)

        logger.info(
            f"Creating collection '{self.collection_name}' "
            f"with hybrid vectors (dense: {ApiToolIndexerConstants.VECTOR_SIZE}d + sparse)"
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                ApiToolIndexerConstants.DENSE_VECTOR_NAME: VectorParams(
                    size=ApiToolIndexerConstants.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                ApiToolIndexerConstants.SPARSE_VECTOR_NAME: SparseVectorParams(
                    index=SparseIndexParams(on_disk=False),
                ),
            },
        )
        logger.success(f"Collection '{self.collection_name}' created successfully")

    def delete_endpoint_point(self, endpoint_id: str) -> bool:
        """Delete the Qdrant point for a given endpoint.

        Used before re-indexing to ensure idempotent updates, and when
        an endpoint is deleted from the mock_endpoints table.

        Args:
            endpoint_id: UUID of the endpoint to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client:
                raise RuntimeError(_CLIENT_NOT_INITIALIZED)

            logger.info(
                f"Deleting existing point for endpoint '{endpoint_id}' from Qdrant"
            )
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[endpoint_id]),
            )
            logger.success(f"Successfully deleted point for endpoint '{endpoint_id}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete point for endpoint '{endpoint_id}': {e}")
            return False

    def upsert_endpoint(self, enriched: EnrichedEndpoint) -> bool:
        """Upsert one enriched endpoint point to Qdrant.

        Args:
            enriched: EnrichedEndpoint with dense/sparse vectors populated

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client:
                raise RuntimeError(_CLIENT_NOT_INITIALIZED)

            logger.info(f"Upserting point for endpoint '{enriched.endpoint_id}'")

            payload = {
                "endpoint_id": enriched.endpoint_id,
                "name": enriched.name,
                "description": enriched.description,
                "url": enriched.url,
                "method": enriched.method,
                "params": enriched.params,
                "enriched_context": enriched.enriched_context,
                "service_id": enriched.service_id,
            }

            vectors: Dict[str, Any] = {
                ApiToolIndexerConstants.DENSE_VECTOR_NAME: enriched.embedding,
            }
            if enriched.sparse_indices:
                vectors[ApiToolIndexerConstants.SPARSE_VECTOR_NAME] = SparseVector(
                    indices=enriched.sparse_indices,
                    values=enriched.sparse_values,
                )

            point = PointStruct(
                id=enriched.endpoint_id,  # use endpoint UUID directly as point ID
                vector=vectors,
                payload=payload,
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            logger.success(
                f"Successfully upserted point for endpoint '{enriched.endpoint_id}'"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to upsert point for endpoint '{enriched.endpoint_id}': {e}"
            )
            return False

    def close(self) -> None:
        """Close Qdrant connection."""
        if self.client:
            logger.info("Closing Qdrant connection")
            self.client.close()
