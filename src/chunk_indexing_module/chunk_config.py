"""Configuration module for chunk retriever."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import os


@dataclass
class ChunkConfig:
    """Configuration for chunk retrieval and embedding operations."""

    # Dataset configuration
    dataset_path: str = "data/datasets"

    # Chunking configuration
    chunk_size: int = 1000
    chunk_overlap: int = 100
    batch_size: int = 10

    # Azure OpenAI Embedding configuration (separate from chat models)
    azure_embedding_endpoint: str = ""
    azure_embedding_api_key: str = ""
    azure_embedding_deployment_name: str = ""
    azure_embedding_api_version: str = ""

    # Qdrant configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "document_chunks"
    qdrant_timeout: float = 30.0

    # Embedding configuration
    embedding_dimension: int = 3072  # text-embedding-3-large dimension

    # Vault configuration
    use_vault: bool = False
    environment: str = "development"
    connection_id: Optional[str] = None

    def __post_init__(self):
        """Load configuration from environment variables or Vault."""
        self.use_vault = os.getenv("USE_VAULT", "false").lower() == "true"
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.connection_id = os.getenv("CONNECTION_ID", self.connection_id)

        if self.use_vault:
            self._load_from_vault()
        else:
            self._load_from_env()

    def _load_from_env(self):
        """Load configuration from environment variables."""
        # Load embedding-specific environment variables
        self.azure_embedding_endpoint = os.getenv(
            "AZURE_EMBEDDING_ENDPOINT", self.azure_embedding_endpoint
        )
        self.azure_embedding_api_key = os.getenv(
            "AZURE_EMBEDDING_API_KEY", self.azure_embedding_api_key
        )
        self.azure_embedding_deployment_name = os.getenv(
            "AZURE_EMBEDDING_DEPLOYMENT_NAME", self.azure_embedding_deployment_name
        )
        self.azure_embedding_api_version = os.getenv(
            "AZURE_EMBEDDING_API_VERSION", self.azure_embedding_api_version
        )

        # Load other configuration from environment
        self.dataset_path = os.getenv("CHUNK_DATASET_PATH", self.dataset_path)
        self.chunk_size = int(os.getenv("CHUNK_SIZE", str(self.chunk_size)))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(self.chunk_overlap)))
        self.batch_size = int(os.getenv("CHUNK_BATCH_SIZE", str(self.batch_size)))

        self.qdrant_host = os.getenv("QDRANT_HOST", self.qdrant_host)
        self.qdrant_port = int(os.getenv("QDRANT_PORT", str(self.qdrant_port)))
        self.qdrant_collection = os.getenv("QDRANT_COLLECTION", self.qdrant_collection)
        self.qdrant_timeout = float(
            os.getenv("QDRANT_TIMEOUT", str(self.qdrant_timeout))
        )

        self.embedding_dimension = int(
            os.getenv("EMBEDDING_DIMENSION", str(self.embedding_dimension))
        )

    def _load_from_vault(self):
        """Load configuration from Vault."""
        try:
            from rag_config_manager.vault import VaultClient, ConnectionManager
            from rag_config_manager.models import Environment

            # Initialize Vault client
            vault_url = os.getenv("VAULT_ADDR", "http://localhost:8200")
            vault_token = os.getenv("VAULT_TOKEN", "myroot")

            vault_client = VaultClient(vault_url=vault_url, token=vault_token)
            connection_manager = ConnectionManager(vault_client)

            # Get current user for vault operations
            current_user = os.getenv("VAULT_USER", "default_user")

            # Map environment string to enum
            env_map = {
                "development": Environment.DEVELOPMENT,
                "staging": Environment.STAGING,
                "production": Environment.PRODUCTION,
                "testing": Environment.TESTING,
            }
            env_enum = env_map.get(self.environment, Environment.DEVELOPMENT)

            # Load embedding configuration
            embedding_configs = self._get_vault_configs(
                connection_manager, current_user, "embedding"
            )
            if embedding_configs:
                embedding_config = self._find_config_for_environment(
                    embedding_configs, env_enum
                )
                if embedding_config:
                    self.azure_embedding_endpoint = (
                        embedding_config.connection_data.get(
                            "endpoint", self.azure_embedding_endpoint
                        )
                    )
                    self.azure_embedding_api_key = embedding_config.connection_data.get(
                        "api_key", self.azure_embedding_api_key
                    )
                    self.azure_embedding_deployment_name = (
                        embedding_config.connection_data.get(
                            "deployment_name", self.azure_embedding_deployment_name
                        )
                    )
                    self.azure_embedding_api_version = (
                        embedding_config.connection_data.get(
                            "api_version", self.azure_embedding_api_version
                        )
                    )
                    self.embedding_dimension = int(
                        embedding_config.connection_data.get(
                            "embedding_dimension", str(self.embedding_dimension)
                        )
                    )

            # Load Qdrant configuration
            qdrant_configs = self._get_vault_configs(
                connection_manager, current_user, "qdrant"
            )
            if qdrant_configs:
                qdrant_config = self._find_config_for_environment(
                    qdrant_configs, env_enum
                )
                if qdrant_config:
                    self.qdrant_host = qdrant_config.connection_data.get(
                        "host", self.qdrant_host
                    )
                    self.qdrant_port = int(
                        qdrant_config.connection_data.get("port", str(self.qdrant_port))
                    )
                    self.qdrant_collection = qdrant_config.connection_data.get(
                        "collection", self.qdrant_collection
                    )
                    self.qdrant_timeout = float(
                        qdrant_config.connection_data.get(
                            "timeout", str(self.qdrant_timeout)
                        )
                    )

            # Load remaining configuration from environment
            self.dataset_path = os.getenv("CHUNK_DATASET_PATH", self.dataset_path)
            self.chunk_size = int(os.getenv("CHUNK_SIZE", str(self.chunk_size)))
            self.chunk_overlap = int(
                os.getenv("CHUNK_OVERLAP", str(self.chunk_overlap))
            )
            self.batch_size = int(os.getenv("CHUNK_BATCH_SIZE", str(self.batch_size)))

            # Override Qdrant config with environment variables if provided
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
            self._load_from_env()

    def _get_vault_configs(
        self, connection_manager: Any, user_id: str, tag: str
    ) -> List[Any]:
        """Get configurations from Vault with specific tag."""
        try:
            connections = connection_manager.list_user_connections(user_id)
            return [conn for conn in connections if tag in conn.metadata.tags]
        except Exception:
            return []

    def _find_config_for_environment(
        self, configs: List[Any], environment: Any
    ) -> Optional[Any]:
        """Find configuration matching the environment."""
        # First try to find exact environment match
        for config in configs:
            if config.metadata.environment == environment:
                return config

        # If no exact match, return the first config
        return configs[0] if configs else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "dataset_path": self.dataset_path,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "batch_size": self.batch_size,
            "azure_embedding_endpoint": self.azure_embedding_endpoint,
            "azure_embedding_api_key": self.azure_embedding_api_key,
            "azure_embedding_deployment_name": self.azure_embedding_deployment_name,
            "azure_embedding_api_version": self.azure_embedding_api_version,
            "qdrant_host": self.qdrant_host,
            "qdrant_port": self.qdrant_port,
            "qdrant_collection": self.qdrant_collection,
            "qdrant_timeout": self.qdrant_timeout,
            "embedding_dimension": self.embedding_dimension,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ChunkConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)

    def validate(self) -> None:
        """Validate configuration parameters."""
        if not self.azure_embedding_endpoint:
            raise ValueError(
                "AZURE_EMBEDDING_ENDPOINT environment variable is required"
            )
        if not self.azure_embedding_api_key:
            raise ValueError("AZURE_EMBEDDING_API_KEY environment variable is required")
        if not self.azure_embedding_deployment_name:
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
