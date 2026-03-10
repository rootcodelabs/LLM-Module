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

RUUTER_SERVICE_BASE_URL = "http://ruuter:8086/services"
"""Base URL for Ruuter public service endpoints (active services)."""

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
"""Number of top results from hybrid search for service identification."""

DENSE_SEARCH_TOP_K = 3
"""Number of top results from dense-only search for relevance scoring."""

# DENSE_MIN_THRESHOLD = 0.38
DENSE_MIN_THRESHOLD = 0.5
"""Minimum dense cosine similarity to consider a result as a potential match.
Below this → skip SERVICE entirely, go to CONTEXT/RAG.
Note: Multilingual embeddings (Estonian/short queries) typically yield
lower cosine scores (0.25-0.40) than English. Tune based on observed scores."""

# DENSE_HIGH_CONFIDENCE_THRESHOLD = 0.40
DENSE_HIGH_CONFIDENCE_THRESHOLD = 0.55
"""Dense cosine similarity for high-confidence service classification.
Above this AND score gap is large → SERVICE without LLM confirmation."""

DENSE_SCORE_GAP_THRESHOLD = 0.05
"""Cosine score gap (top - second) for high-confidence classification.
Ensures the top result is significantly better than the runner-up."""
