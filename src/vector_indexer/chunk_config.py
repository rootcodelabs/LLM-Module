"""Configuration module for chunk retriever."""

from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import Dict, Any, Optional
import os


class ChunkConfig(BaseModel):
    """Configuration for chunk retrieval and embedding operations."""

    # Dataset configuration
    dataset_path: str = "data/datasets"

    # Chunking configuration
    chunk_size: int = Field(default=1000, gt=0, description="Size of text chunks")
    chunk_overlap: int = Field(default=100, ge=0, description="Overlap between chunks")
    batch_size: int = Field(default=10, gt=0, description="Batch size for processing")

    # Azure OpenAI Embedding configuration (separate from chat models)
    azure_embedding_endpoint: str = ""
    azure_embedding_api_key: str = ""
    azure_embedding_deployment_name: str = ""
    azure_embedding_api_version: str = ""

    # Qdrant configuration
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "document_chunks"
    qdrant_timeout: float = 30.0

    # Embedding configuration
    embedding_dimension: int = Field(
        default=3072, gt=0, description="Embedding dimension"
    )

    # Vault configuration
    use_vault: bool = False
    environment: str = "production"
    connection_id: Optional[str] = None

    model_config = {
        "validate_assignment": True,
        "extra": "allow",  # Allow extra fields for backward compatibility
        "arbitrary_types_allowed": True,
    }

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info: ValidationInfo) -> int:
        """Validate that chunk_overlap is less than chunk_size."""
        if info.data and "chunk_size" in info.data:
            chunk_size: int = info.data["chunk_size"]
            if v >= chunk_size:
                raise ValueError("chunk_overlap must be less than chunk_size")
        return v

    def __init__(self, **kwargs: Any):
        """Initialize ChunkConfig with Pydantic validation."""
        super().__init__(**kwargs)
        self.__post_init__()

    def __post_init__(self):
        """Load configuration from environment variables or Vault."""
        self.use_vault = True  # Default to true
        # self.environment and self.connection_id are already set by dataclass initialization

        self._load_from_vault()

    def _load_from_vault(self):
        """Load configuration from Vault."""
        try:
            from vector_indexer.vault.secret_resolver import (
                EmbeddingSecretResolver,
            )

            # Initialize embedding secret resolver
            resolver = EmbeddingSecretResolver()

            # Get embedding configuration
            embedding_secret = None

            if self.environment == "production":
                # For production: Get first available embedding model
                embedding_secret = resolver.get_first_available_model(
                    provider="azure_openai", environment=self.environment
                )
            else:
                # For dev/test: Use connection_id to find specific model
                if self.connection_id:
                    # Try to find the specific model - for now using text-embedding-3-large as default
                    embedding_secret = resolver.get_secret_for_model(
                        provider="azure_openai",
                        environment=self.environment,
                        model_name="text-embedding-3-large",
                        connection_id=self.connection_id,
                    )
                else:
                    print(
                        "Warning: connection_id required for non-production environments"
                    )

            if embedding_secret:
                # Update configuration with secrets from vault
                self.azure_embedding_endpoint = embedding_secret.endpoint
                self.azure_embedding_api_key = embedding_secret.api_key
                self.azure_embedding_deployment_name = embedding_secret.deployment_name
                self.azure_embedding_api_version = embedding_secret.api_version
                self.embedding_dimension = embedding_secret.embedding_dimension

                print(
                    f"Successfully loaded embedding configuration from vault for {self.environment}"
                )
            else:
                print(
                    f"Warning: No embedding configuration found in vault for {self.environment}"
                )
                print("Falling back to environment variables")

            # Load remaining configuration from environment
            self.dataset_path = os.getenv("CHUNK_DATASET_PATH", self.dataset_path)
            self.chunk_size = int(os.getenv("CHUNK_SIZE", str(self.chunk_size)))
            self.chunk_overlap = int(
                os.getenv("CHUNK_OVERLAP", str(self.chunk_overlap))
            )
            self.batch_size = int(os.getenv("CHUNK_BATCH_SIZE", str(self.batch_size)))

            # Qdrant configuration - keeping from environment for now
            self.qdrant_host = os.getenv("QDRANT_HOST", self.qdrant_host)
            self.qdrant_port = int(os.getenv("QDRANT_PORT", str(self.qdrant_port)))
            self.qdrant_collection = os.getenv(
                "QDRANT_COLLECTION", self.qdrant_collection
            )
            self.qdrant_timeout = float(
                os.getenv("QDRANT_TIMEOUT", str(self.qdrant_timeout))
            )

        except Exception as e:
            print(f"Warning: Failed to load configuration from Vault: {e}")
            print("Falling back to environment variables")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ChunkConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)

    def validate_config(self) -> None:
        """Validate configuration parameters."""
        # Only check for these values when not using vault or when vault loading failed
        if not self.azure_embedding_endpoint:
            if self.use_vault:
                raise ValueError("Failed to load embedding endpoint from vault")
            else:
                raise ValueError(
                    "AZURE_EMBEDDING_ENDPOINT environment variable is required"
                )

        if not self.azure_embedding_api_key:
            if self.use_vault:
                raise ValueError("Failed to load embedding API key from vault")
            else:
                raise ValueError(
                    "AZURE_EMBEDDING_API_KEY environment variable is required"
                )

        if not self.azure_embedding_deployment_name:
            if self.use_vault:
                raise ValueError("Failed to load embedding deployment name from vault")
            else:
                raise ValueError(
                    "AZURE_EMBEDDING_DEPLOYMENT_NAME environment variable is required"
                )

        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
