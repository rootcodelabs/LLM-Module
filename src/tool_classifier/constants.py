"""Constants and configuration for tool classifier module."""


# ============================================================================
# Qdrant Vector Database Configuration
# ============================================================================

QDRANT_HOST = "qdrant"
"""Qdrant server hostname."""

QDRANT_PORT = 6333
"""Qdrant server port."""

QDRANT_TIMEOUT = 10.0
"""Qdrant HTTP client timeout in seconds."""


# ============================================================================
# Semantic Search Configuration
# ============================================================================

QDRANT_COLLECTION = "intent_collections"
"""Qdrant collection name for service intent search."""

SEMANTIC_SEARCH_TOP_K = 10
"""Number of top services to return from semantic search."""

SEMANTIC_SEARCH_THRESHOLD = 0.2
"""Minimum similarity score threshold for semantic search (0.0-1.0).
Lowered from 0.4 to handle broader queries."""


# ============================================================================
# Ruuter Service Configuration
# ============================================================================

RUUTER_BASE_URL = "http://ruuter-private:8086"
"""Base URL for Ruuter private service endpoints."""

RAG_SEARCH_RUUTER_PUBLIC = "http://ruuter-public:8086/rag-search"
"""Public Ruuter endpoint for RAG search service discovery."""

SERVICE_CALL_TIMEOUT = 10
"""Timeout in seconds for external service calls via Ruuter."""

SERVICE_DISCOVERY_TIMEOUT = 10.0
"""Timeout in seconds for service discovery calls."""


# ============================================================================
# Service Workflow Thresholds
# ============================================================================

MAX_SERVICES_FOR_LLM_CONTEXT = 50
"""Maximum number of services to send to LLM without semantic filtering.
If service count exceeds this, semantic search is used to filter to top-K."""

SERVICE_COUNT_THRESHOLD = 10
"""Threshold for triggering semantic search. If service count > this value,
semantic search is used instead of sending all services to LLM."""


# ============================================================================
# Hybrid Search Classification Thresholds
# ============================================================================

HYBRID_SEARCH_TOP_K = 5
"""Number of top results from hybrid search for classification."""

HYBRID_SEARCH_MIN_THRESHOLD = 0.01
"""Minimum RRF score to consider a result as a potential match."""

SCORE_RATIO_THRESHOLD = 2.0
"""Score ratio (top/second) for confident service classification.
If the top result's RRF score is > 2x the second result, it's a high-confidence match."""

SCORE_GAP_THRESHOLD = 0.005
"""Absolute score gap for confident classification.
Prevents false positives when both scores are very low."""
