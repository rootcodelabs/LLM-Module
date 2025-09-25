"""Data models for RAG Config Manager using Pydantic."""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    """Supported provider types."""

    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    QDRANT = "qdrant"


class Environment(str, Enum):
    """Environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class AzureOpenAIConnection(BaseModel):
    """Azure OpenAI connection configuration."""

    endpoint: str
    api_key: str
    deployment_name: str
    api_version: str = "2025-01-01-preview"


class AWSConnection(BaseModel):
    """AWS connection configuration."""

    region: str
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None


class QdrantConnection(BaseModel):
    """Qdrant connection configuration."""

    host: str = "localhost"
    port: int = 6333
    collection: str = "document_chunks"
    timeout: float = 30.0
    api_key: Optional[str] = None
    url: Optional[str] = None


class ConnectionMetadata(BaseModel):
    """Connection metadata information."""

    id: str = Field(default_factory=lambda: f"conn_{uuid.uuid4().hex[:8]}")
    name: str
    description: str
    provider: ProviderType
    environment: Environment
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_default: bool = False


class Connection(BaseModel):
    """Complete connection with data and metadata."""

    metadata: ConnectionMetadata
    connection_data: Dict[
        str, Any
    ]  # Will hold AzureOpenAIConnection or AWSConnection as dict

    def get_connection_object(self):
        """Get the typed connection object based on provider."""
        if self.metadata.provider == ProviderType.AZURE_OPENAI:
            return AzureOpenAIConnection(**self.connection_data)
        elif self.metadata.provider == ProviderType.AWS_BEDROCK:
            return AWSConnection(**self.connection_data)
        elif self.metadata.provider == ProviderType.QDRANT:
            return QdrantConnection(**self.connection_data)
        else:
            return self.connection_data


class UsageStats(BaseModel):
    """Connection usage statistics."""

    connection_id: str
    total_usage: int
    last_used: Optional[datetime]
    daily_usage: Dict[str, int] = Field(default_factory=dict)  # date -> count
    monthly_usage: Dict[str, int] = Field(default_factory=dict)  # month -> count
