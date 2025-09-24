"""Embedding vault module for chunk indexing."""

from chunk_indexing_module.vault.vault_client import EmbeddingVaultClient
from chunk_indexing_module.vault.secret_resolver import EmbeddingSecretResolver
from chunk_indexing_module.vault.models import (
    AzureEmbeddingSecret,
    get_embedding_secret_model,
)
from chunk_indexing_module.vault.exceptions import (
    EmbeddingVaultError,
    EmbeddingVaultConnectionError,
    EmbeddingVaultSecretError,
    EmbeddingVaultTokenError,
)

__all__ = [
    "EmbeddingVaultClient",
    "EmbeddingSecretResolver",
    "AzureEmbeddingSecret",
    "get_embedding_secret_model",
    "EmbeddingVaultError",
    "EmbeddingVaultConnectionError",
    "EmbeddingVaultSecretError",
    "EmbeddingVaultTokenError",
]
