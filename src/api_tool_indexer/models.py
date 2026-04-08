"""Data models for the API Tool Indexer."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParamSchema(BaseModel):
    """Schema for a single API endpoint parameter."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(
        ...,
        description="Parameter type: string, date, integer, boolean, number",
    )
    required: bool = Field(..., description="Whether this parameter is required")
    description: str = Field(
        ..., description="Human-readable description of the parameter"
    )


class EndpointData(BaseModel):
    """Raw endpoint data fetched from the mock_endpoints table.

    This is the input to the indexing pipeline.
    """

    endpoint_id: str = Field(..., description="UUID of the endpoint")
    name: str = Field(..., description="Endpoint name (snake_case)")
    description: str = Field(..., description="Human-readable description")
    url: str = Field(..., description="Full URL of the external API")
    method: str = Field(..., description="HTTP method: GET or POST")
    params: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of parameter schemas [{name, type, required, description}]",
    )
    service_id: Optional[str] = Field(
        default=None, description="Optional parent service UUID"
    )
    visibility: str = Field(default="private", description="public or private")
    type: str = Field(default="custom_endpoint", description="Endpoint type")


class EnrichedEndpoint(BaseModel):
    """Enriched endpoint data ready for storage in Qdrant api_tool_collection.

    One point per endpoint is stored.
    The payload stored in Qdrant includes all fields needed by the agentic loop
    so no additional DB roundtrip is needed after a semantic match.
    """

    endpoint_id: str = Field(..., description="UUID of the endpoint")
    name: str = Field(..., description="Endpoint name")
    description: str = Field(..., description="Raw description from DB")
    url: str = Field(..., description="Full URL of the external API")
    method: str = Field(..., description="HTTP method: GET or POST")
    params: List[Dict[str, Any]] = Field(
        ...,
        description="Full params schema — stored in payload for direct use by agentic loop",
    )
    enriched_context: str = Field(
        ..., description="LLM-generated rich context for better semantic matching"
    )
    service_id: Optional[str] = Field(default=None, description="Parent service UUID")

    # Vector fields (populated by indexer pipeline)
    embedding: List[float] = Field(
        default_factory=list, description="Dense embedding vector (3072-dim)"
    )
    sparse_indices: List[int] = Field(
        default_factory=list, description="Sparse vector indices (BM25)"
    )
    sparse_values: List[float] = Field(
        default_factory=list, description="Sparse vector values (BM25)"
    )


class IndexingResult(BaseModel):
    """Result of a single endpoint indexing operation."""

    success: bool = Field(..., description="Whether indexing succeeded")
    endpoint_id: str = Field(..., description="Endpoint UUID")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(default=None, description="Error message if failed")
