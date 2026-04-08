"""Constants for the API Tool Indexer module."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiToolIndexerConstants:
    """Constants for the API tool indexing pipeline."""

    # Qdrant Configuration
    COLLECTION_NAME = "api_tool_collection"
    DEFAULT_QDRANT_HOST = "qdrant"
    DEFAULT_QDRANT_PORT = 6333

    # Vector Configuration - mirrors intent_collections for consistency
    VECTOR_SIZE = 3072  # text-embedding-3-large dimension (Azure)
    DISTANCE_METRIC = "Cosine"

    # Named Vector Names (hybrid search: dense + sparse)
    DENSE_VECTOR_NAME = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    # LLM / Embedding API
    DEFAULT_API_BASE_URL = "http://llm-orchestration-service:8100"
    DEFAULT_ENVIRONMENT = "production"
    DEFAULT_CONNECTION_ID = "gpt-4o-mini"

    # Retry Configuration
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # Exponential backoff base (2^attempt seconds)
    REQUEST_TIMEOUT = 60  # seconds

    # Context Enrichment Template
    # Used to generate a rich semantic context for each endpoint before embedding
    CONTEXT_TEMPLATE = """<document>
{full_endpoint_info}
</document>

Here is the API endpoint we want to enrich for better semantic search retrieval:
<endpoint>
Name: {name}
Description: {description}
Parameters: {params_summary}
</endpoint>

Please generate a rich, detailed context that describes this API endpoint comprehensively for semantic search.
Include information about:
- What the user wants to accomplish by calling this endpoint
- Key terms and synonyms for this action
- Related concepts and use cases
- Common ways users might ask for this functionality in natural language

IMPORTANT: Generate the context in the SAME LANGUAGE as the endpoint description above. If the description is in Estonian, respond in Estonian. If in English, respond in English. If in Russian, respond in Russian.

Answer only with the enriched context and nothing else."""
