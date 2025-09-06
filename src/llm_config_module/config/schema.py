"""Configuration schema definitions for the LLM Config Module."""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..types import LLMProvider


@dataclass
class ProviderConfig:
    """Base configuration for LLM providers."""

    enabled: bool
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "enabled": self.enabled,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }


@dataclass
class AzureOpenAIConfig(ProviderConfig):
    """Configuration for Azure OpenAI provider."""

    endpoint: str = ""
    api_key: str = ""
    api_version: str = "2024-02-15-preview"
    deployment_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "endpoint": self.endpoint,
                "api_key": self.api_key,
                "api_version": self.api_version,
                "deployment_name": self.deployment_name,
            }
        )
        return base_dict


@dataclass
class AWSBedrockConfig(ProviderConfig):
    """Configuration for AWS Bedrock provider."""

    region: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    session_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "region": self.region,
                "access_key_id": self.access_key_id,
                "secret_access_key": self.secret_access_key,
                "session_token": self.session_token,
            }
        )
        return base_dict


@dataclass
class LLMConfiguration:
    """Main configuration container for LLM settings."""

    default_provider: LLMProvider
    providers: Dict[str, ProviderConfig]

    def get_provider_config(self, provider: LLMProvider) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider."""
        return self.providers.get(provider.value)

    def is_provider_enabled(self, provider: LLMProvider) -> bool:
        """Check if a provider is enabled."""
        config = self.get_provider_config(provider)
        return config is not None and config.enabled
