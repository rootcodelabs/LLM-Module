"""API Endpoint Indexer Pipeline.

Receives raw API EndpointData, enriches it with LLM-generated context,
creates hybrid embeddings (dense + sparse), and stores the result in Qdrant
api_tool_collection as a single point per endpoint.

Pipeline steps:
    1. Build LLM prompt from endpoint name, description, and params
    2. Generate context via LLMAPIClient.generate_context()
    3. Build embed text: name + description + context + param descriptions
    4. Create dense embedding via LLMAPIClient.create_embedding()
    5. Create sparse vector via compute_sparse_vector()
    6. Delete existing Qdrant point for idempotent update
    7. Upsert EnrichedEndpoint to api_tool_collection
    8. Return IndexingResult
"""

import sys
import json
import asyncio
import argparse
from typing import List
from loguru import logger

from api_tool_indexer.constants import ApiToolIndexerConstants
from api_tool_indexer.models import EndpointData, EnrichedEndpoint, IndexingResult
from api_tool_indexer.qdrant_manager import ApiToolQdrantManager

# Reuse LLMAPIClient from intent_data_enrichment.
from intent_data_enrichment.api_client import LLMAPIClient

# Reuse sparse encoder from tool_classifier (shared BM25 implementation).
sys.path.insert(0, "/app/src")
try:
    from tool_classifier.sparse_encoder import compute_sparse_vector
except ImportError:
    try:
        from src.tool_classifier.sparse_encoder import compute_sparse_vector
    except ImportError:
        logger.warning(
            "Could not import sparse_encoder from tool_classifier, "
            "attempting direct import"
        )
        import importlib.util
        import os

        module_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tool_classifier",
            "sparse_encoder.py",
        )
        if os.path.exists(module_path):
            spec = importlib.util.spec_from_file_location("sparse_encoder", module_path)
            if spec is not None and spec.loader is not None:
                sparse_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(sparse_module)
                compute_sparse_vector = sparse_module.compute_sparse_vector
            else:
                raise ImportError(
                    f"Cannot load spec or loader for sparse_encoder.py at {module_path}"
                ) from None
        else:
            raise ImportError(
                f"Cannot find sparse_encoder.py at {module_path}"
            ) from None


def _build_params_summary(params: list) -> str:
    """Build a readable one-liner of params for LLM prompt and embedding.

    Example output:
        'countryIsoCode (string, required): ISO country code; validFrom (date, required): Start date'

    Args:
        params: List of param dicts with name, type, required, description keys.

    Returns:
        Empty string if no params, otherwise a semicolon-separated summary.
    """
    if not params:
        return "No parameters required."

    parts: List[str] = []
    for p in params:
        name = p.get("name", "unknown")
        ptype = p.get("type", "string")
        required = "required" if p.get("required", False) else "optional"
        description = p.get("description", "")
        parts.append(f"{name} ({ptype}, {required}): {description}")

    return "; ".join(parts)


async def _generate_context_for_endpoint(
    api_client: LLMAPIClient,
    endpoint_data: EndpointData,
) -> str:
    """Generate a rich LLM context for an API endpoint.

    Args:
        api_client: Initialized LLMAPIClient.
        endpoint_data: Raw endpoint data from mock_endpoints table.

    Returns:
        LLM-generated enriched context string.

    Raises:
        RuntimeError: If context generation fails after all retries.
    """
    params_summary = _build_params_summary(endpoint_data.params)

    logger.info(f"params_summary : {params_summary}")

    full_endpoint_info = (
        f"Endpoint: {endpoint_data.name}\n"
        f"Method: {endpoint_data.method}\n"
        f"URL: {endpoint_data.url}\n"
        f"Description: {endpoint_data.description}\n"
        f"Parameters: {params_summary}"
    )

    context_prompt = ApiToolIndexerConstants.CONTEXT_TEMPLATE.format(
        full_endpoint_info=full_endpoint_info,
        name=endpoint_data.name,
        description=endpoint_data.description,
        params_summary=params_summary,
    )

    logger.debug(
        "Generated context prompt for endpoint '{}': {} chars",
        endpoint_data.endpoint_id,
        len(context_prompt),
    )

    # context_type="api_tool" makes context_manager use API_TOOL_CONTEXT_PROMPT,
    # which passes chunk_prompt through unmodified so CHUNK_CONTEXT_PROMPT cannot
    # override the instructions in CONTEXT_TEMPLATE (e.g. example query generation).
    request_data = {
        "document_prompt": "",
        "chunk_prompt": context_prompt,
        "environment": api_client.environment,
        "use_cache": False,
        "connection_id": api_client.connection_id,
        "context_type": "api_tool",
    }

    last_error = None
    for attempt in range(api_client.max_retries):
        try:
            logger.info(
                f"Generating context for endpoint '{endpoint_data.endpoint_id}' "
                f"(attempt {attempt + 1}/{api_client.max_retries})"
            )

            if not api_client.session:
                raise RuntimeError("HTTP session not initialized")

            response = await api_client.session.post(
                f"{api_client.api_base_url}/generate-context", json=request_data
            )
            response.raise_for_status()
            result = response.json()

            context = result.get("context", "").strip()

            logger.debug(
                "context preview: {}{}",
                context[:200].replace("\n", "\\n"),
                "..." if len(context) > 200 else "",
            )

            if not context:
                raise ValueError("Empty context returned from API")

            logger.success(
                f"Context generated for endpoint '{endpoint_data.endpoint_id}': "
                f"{len(context)} characters"
            )
            return context

        except Exception as e:
            last_error = e
            logger.warning(
                f"Context generation attempt {attempt + 1} failed for "
                f"'{endpoint_data.endpoint_id}': {e}"
            )
            if attempt < api_client.max_retries - 1:
                delay = api_client.retry_delay_base**attempt
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

    error_msg = (
        f"Context generation failed for '{endpoint_data.endpoint_id}' "
        f"after {api_client.max_retries} attempts: {last_error}"
    )
    logger.error(error_msg)
    raise RuntimeError(error_msg)


async def index_endpoint(endpoint_data: EndpointData) -> IndexingResult:
    """Index one API endpoint into Qdrant api_tool_collection.

    Args:
        endpoint_data: Raw endpoint data from mock_endpoints table.

    Returns:
        IndexingResult indicating success or failure with details.
    """
    endpoint_id = endpoint_data.endpoint_id
    logger.info(
        f"Starting indexing pipeline for endpoint '{endpoint_id}' "
        f"(name='{endpoint_data.name}')"
    )

    try:
        # Steps 1–5: LLM enrichment and embedding
        async with LLMAPIClient(
            api_base_url=ApiToolIndexerConstants.DEFAULT_API_BASE_URL,
            environment=ApiToolIndexerConstants.DEFAULT_ENVIRONMENT,
            connection_id=ApiToolIndexerConstants.DEFAULT_CONNECTION_ID,
            max_retries=ApiToolIndexerConstants.MAX_RETRIES,
            retry_delay_base=ApiToolIndexerConstants.RETRY_DELAY_BASE,
            timeout=ApiToolIndexerConstants.REQUEST_TIMEOUT,
        ) as api_client:
            # Step 1-2: Generate LLM enriched context
            logger.info("Step 1/5: Generating LLM enriched context")
            enriched_context = await _generate_context_for_endpoint(
                api_client, endpoint_data
            )

            # Step 3: Build embed text combining all semantic signal
            params_summary = _build_params_summary(endpoint_data.params)
            embed_text = (
                f"{endpoint_data.name}. "
                f"{endpoint_data.description}. "
                f"{enriched_context}. "
                f"Parameters: {params_summary}"
            )

            # Step 4: Create dense embedding vector
            logger.info("Step 2/5: Creating dense embedding vector")
            dense_embedding = await api_client.create_embedding(embed_text)

        # Step 5: Create sparse (BM25) vector - synchronous, after closing HTTP session
        logger.info("Step 3/5: Computing sparse (BM25) vector")
        sparse_vec = compute_sparse_vector(embed_text)

        # Build EnrichedEndpoint ready for Qdrant storage
        enriched = EnrichedEndpoint(
            endpoint_id=endpoint_id,
            name=endpoint_data.name,
            description=endpoint_data.description,
            url=endpoint_data.url,
            method=endpoint_data.method,
            params=endpoint_data.params,
            enriched_context=enriched_context,
            service_id=endpoint_data.service_id,
            embedding=dense_embedding,
            sparse_indices=sparse_vec.indices,
            sparse_values=sparse_vec.values,
        )

        # Steps 6-7: Qdrant operations (separate try/finally ensures connection is closed)
        qdrant = ApiToolQdrantManager()
        try:
            qdrant.connect()
            qdrant.ensure_collection()

            # Step 6: Delete existing point for idempotent update
            logger.info("Step 4/5: Deleting existing Qdrant point (idempotent update)")
            deleted = qdrant.delete_endpoint_point(endpoint_id)
            if not deleted:
                logger.error(
                    f"Failed to delete existing Qdrant point for endpoint '{endpoint_id}'. "
                    "Aborting upsert to prevent stale data."
                )
                return IndexingResult(
                    success=False,
                    endpoint_id=endpoint_id,
                    message="Qdrant delete failed before upsert",
                    error="delete_endpoint_point returned False",
                )

            # Step 7: Upsert the enriched endpoint
            logger.info("Step 5/5: Upserting endpoint into api_tool_collection")
            upserted = qdrant.upsert_endpoint(enriched)

        finally:
            qdrant.close()

        # Step 8: Return result
        if upserted:
            logger.success(
                f"Endpoint '{endpoint_id}' (name='{endpoint_data.name}') "
                "indexed successfully"
            )
            return IndexingResult(
                success=True,
                endpoint_id=endpoint_id,
                message=(
                    f"Endpoint '{endpoint_data.name}' indexed successfully into "
                    f"api_tool_collection (dim={len(dense_embedding)})"
                ),
            )
        else:
            return IndexingResult(
                success=False,
                endpoint_id=endpoint_id,
                message="Qdrant upsert failed",
                error="upsert_endpoint returned False",
            )

    except Exception as e:
        logger.error(f"Indexing pipeline failed for endpoint '{endpoint_id}': {e}")
        return IndexingResult(
            success=False,
            endpoint_id=endpoint_id,
            message="Indexing pipeline failed with an unexpected error",
            error=str(e),
        )


def parse_arguments() -> EndpointData:
    """Parse command line arguments into EndpointData model."""
    parser = argparse.ArgumentParser(description="API Tool Indexing")
    parser.add_argument("--endpoint-id", type=str, required=True, help="Endpoint ID")
    parser.add_argument("--name", type=str, required=True, help="Endpoint name")
    parser.add_argument(
        "--description", type=str, required=True, help="Endpoint description"
    )
    parser.add_argument("--url", type=str, required=True, help="Endpoint URL")
    parser.add_argument("--service-id", type=str, default="", help="Parent service ID")
    parser.add_argument("--method", type=str, default="GET", help="HTTP method")
    parser.add_argument("--visibility", type=str, default="public", help="Visibility")
    parser.add_argument(
        "--type", type=str, default="custom_endpoint", help="Endpoint type"
    )
    parser.add_argument("--params-file", type=str, help="Path to params JSON file")

    args = parser.parse_args()

    # Read and parse JSON array from file
    params = []
    if args.params_file:
        try:
            with open(args.params_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    params = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read/parse params file: {e}")

    return EndpointData(
        endpoint_id=args.endpoint_id,
        service_id=args.service_id,
        name=args.name,
        description=args.description,
        method=args.method,
        url=args.url,
        visibility=args.visibility,
        type=args.type,
        params=params,
    )


def main() -> int:
    """Main entry point for API tool indexing via CLI."""
    logger.info("Starting API Tool indexing pipeline...")

    try:
        # Parse arguments
        endpoint_data = parse_arguments()
        logger.info(f"Endpoint ID: {endpoint_data.endpoint_id}")
        logger.info(f"Endpoint Name: {endpoint_data.name}")
        logger.info(f"Params count: {len(endpoint_data.params)}")

        # Run indexing pipeline
        result = asyncio.run(index_endpoint(endpoint_data))

        # Log results
        if result.success:
            logger.success("Indexing completed successfully")
            logger.info(f"Endpoint: {result.endpoint_id}")
            logger.info(f"Message: {result.message}")
            return 0
        else:
            logger.error("Indexing failed")
            logger.error(f"Endpoint: {result.endpoint_id}")
            logger.error(f"Message: {result.message}")
            logger.error(f"Error: {result.error}")
            return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
