"""Qdrant manager for intent collections."""

import uuid
from typing import Optional
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from data_enrichment.constants import EnrichmentConstants
from data_enrichment.models import EnrichedService

# Error messages
_CLIENT_NOT_INITIALIZED = "Qdrant client not initialized"


class QdrantManager:
    """Manages Qdrant operations for intent collections."""

    def __init__(
        self,
        host: str = EnrichmentConstants.DEFAULT_QDRANT_HOST,
        port: int = EnrichmentConstants.DEFAULT_QDRANT_PORT,
        collection_name: str = EnrichmentConstants.COLLECTION_NAME,
    ) -> None:
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.client: Optional[QdrantClient] = None

    def connect(self) -> None:
        """Connect to Qdrant."""
        try:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}")
            # Suppress version compatibility warning (client 1.17.0 vs server 1.15.1)
            # Minor version difference is acceptable (see warning in logs)
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
        """Ensure the intent_collections collection exists with correct vector size."""
        try:
            if not self.client:
                raise RuntimeError(_CLIENT_NOT_INITIALIZED)

            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]

            if self.collection_name in collection_names:
                # Check if existing collection has correct vector size
                collection_info = self.client.get_collection(self.collection_name)
                
                # Qdrant vectors config is a dict - get the default vector config
                vectors_config = collection_info.config.params.vectors
                
                existing_vector_size: Optional[int] = None
                if isinstance(vectors_config, dict):
                    # Get first vector config (usually the default/unnamed one)
                    if vectors_config:
                        vector_params = next(iter(vectors_config.values()))
                        existing_vector_size = vector_params.size
                elif vectors_config is not None:
                    # Direct VectorParams object (older API)
                    existing_vector_size = vectors_config.size
                
                if existing_vector_size is None:
                    logger.warning(f"Could not determine vector size for '{self.collection_name}', recreating")
                    self.client.delete_collection(self.collection_name)
                    self._create_collection()
                elif existing_vector_size != EnrichmentConstants.VECTOR_SIZE:
                    logger.warning(
                        f"Collection '{self.collection_name}' exists with wrong vector size: "
                        f"{existing_vector_size} (expected {EnrichmentConstants.VECTOR_SIZE})"
                    )
                    logger.info(f"Deleting and recreating collection '{self.collection_name}'")
                    self.client.delete_collection(self.collection_name)
                    self._create_collection()
                else:
                    logger.info(
                        f"Collection '{self.collection_name}' already exists "
                        f"with correct vector size ({existing_vector_size})"
                    )
            else:
                self._create_collection()

        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}")
            raise

    def _create_collection(self) -> None:
        """Create the collection with correct vector configuration."""
        if not self.client:
            raise RuntimeError(_CLIENT_NOT_INITIALIZED)
            
        logger.info(
            f"Creating collection '{self.collection_name}' "
            f"with vector size {EnrichmentConstants.VECTOR_SIZE}"
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=EnrichmentConstants.VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.success(f"Collection '{self.collection_name}' created successfully")

    def upsert_service(self, enriched_service: EnrichedService) -> bool:
        """
        Upsert enriched service to Qdrant (update if exists, insert if new).

        Args:
            enriched_service: Enric_CLIENT_NOT_INITIALIZED

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client:
                raise RuntimeError("Qdrant client not initialized")

            logger.info(f"Upserting service '{enriched_service.id}' to Qdrant")

            # Convert service_id to UUID for Qdrant compatibility
            # Qdrant requires point IDs to be either integers or UUIDs
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, enriched_service.id))
            logger.debug(f"Generated UUID: {point_id} for service_id: {enriched_service.id}")

            # Prepare payload (all metadata except embedding)
            payload = {
                "service_id": enriched_service.id,  # Store original ID in payload
                "name": enriched_service.name,
                "description": enriched_service.description,
                "examples": enriched_service.examples,
                "entities": enriched_service.entities,
                "context": enriched_service.context,
            }

            # Create point with UUID
            point = PointStruct(
                id=point_id,  # ✓ Now using UUID string
                vector=enriched_service.embedding,
                payload=payload,
            )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )

            logger.success(
                f"Successfully upserted service '{enriched_service.id}' "
                f"({len(enriched_service.embedding)}-dim vector)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to upsert service '{enriched_service.id}': {e}")
            return False

    def close(self) -> None:
        """Close Qdrant connection."""
        if self.client:
            logger.info("Closing Qdrant connection")
            self.client.close()
