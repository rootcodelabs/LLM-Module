"""Vault integration for LLM Config Module."""

from llm_config_module.vault.secret_resolver import SecretResolver
from llm_config_module.vault.vault_client import VaultAgentClient
from llm_config_module.vault.models import AzureOpenAISecret, AWSBedrockSecret
from llm_config_module.vault.exceptions import VaultSecretError, VaultConnectionError

__all__ = [
    "SecretResolver",
    "VaultAgentClient",
    "AzureOpenAISecret",
    "AWSBedrockSecret",
    "VaultSecretError",
    "VaultConnectionError",
]
