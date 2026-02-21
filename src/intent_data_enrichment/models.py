"""Data models for service enrichment."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ServiceData(BaseModel):
    """Input service data to be enriched."""

    service_id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Service name")
    description: str = Field(..., description="Service description")
    examples: List[str] = Field(default_factory=list, description="Example queries")
    entities: List[str] = Field(
        default_factory=list, description="Expected entity names"
    )
    ruuter_type: Optional[str] = Field(default="GET", description="HTTP method")
    current_state: Optional[str] = Field(default="draft", description="Service state")
    is_common: Optional[bool] = Field(default=False, description="Is common service")


class EnrichedService(BaseModel):
    """Enriched service data ready for storage."""

    id: str = Field(..., description="Service ID (maps to service_id)")
    name: str = Field(..., description="Service name")
    description: str = Field(..., description="Service description")
    examples: List[str] = Field(..., description="Example queries")
    entities: List[str] = Field(..., description="Expected entity names")
    context: str = Field(..., description="Generated rich context")
    embedding: List[float] = Field(..., description="Context embedding vector")


class EnrichmentResult(BaseModel):
    """Result of enrichment operation."""

    success: bool = Field(..., description="Whether enrichment succeeded")
    service_id: str = Field(..., description="Service ID")
    message: str = Field(..., description="Result message")
    context_length: Optional[int] = Field(None, description="Generated context length")
    embedding_dimension: Optional[int] = Field(
        None, description="Embedding vector dimension"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
