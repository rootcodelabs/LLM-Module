"""Configuration loader for the LLM Config Module."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .schema import (
    LLMConfiguration,
    ProviderConfig,
    AzureOpenAIConfig,
    AWSBedrockConfig,
)
from ..types import LLMProvider
from ..exceptions import ConfigurationError, InvalidConfigurationError


class ConfigurationLoader:
    """Loads and processes LLM configuration from YAML files with environment variable support."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize the configuration loader.

        Args:
            config_path: Path to the configuration file. If None, uses default location.
        """
        self.config_path = self._resolve_config_path(config_path)

    def _resolve_config_path(self, config_path: Optional[str]) -> Path:
        """Resolve the configuration file path."""
        if config_path:
            return Path(config_path)

        # Default locations to search for config
        default_locations = [
            Path("llm_config.yaml"),
            Path("config/llm_config.yaml"),
            Path(__file__).parent / "llm_config.yaml",
        ]

        for location in default_locations:
            if location.exists():
                return location

        # If no config file found, use the default location in the config directory
        return Path(__file__).parent / "llm_config.yaml"

    def load_config(self) -> LLMConfiguration:
        """Load and parse the configuration file.

        Returns:
            Parsed LLM configuration.

        Raises:
            ConfigurationError: If configuration loading fails.
        """
        try:
            if not self.config_path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {self.config_path}"
                )

            with open(self.config_path, "r", encoding="utf-8") as file:
                raw_config = yaml.safe_load(file)

            if not raw_config or "llm" not in raw_config:
                raise ConfigurationError("Invalid configuration: missing 'llm' section")

            # Process environment variables
            processed_config = self._process_environment_variables(raw_config["llm"])

            # Parse and validate configuration
            return self._parse_configuration(processed_config)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Failed to parse YAML configuration: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e

    def _process_environment_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variable substitutions in configuration.

        Args:
            config: Raw configuration dictionary.

        Returns:
            Configuration with environment variables substituted.
        """

        def substitute_env_vars(obj: Any) -> Any:
            if isinstance(obj, str):
                # Pattern to match ${VAR_NAME} or ${VAR_NAME:default_value}
                pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

                def replace_env_var(match: re.Match[str]) -> str:
                    var_name = match.group(1)
                    default_value = match.group(2) if match.group(2) is not None else ""
                    return os.getenv(var_name, default_value)

                return re.sub(pattern, replace_env_var, obj)
            elif isinstance(obj, dict):
                result: Dict[str, Any] = {}
                for key, value in obj.items():  # type: ignore[misc]
                    result[str(key)] = substitute_env_vars(value)  # type: ignore[arg-type]
                return result
            elif isinstance(obj, list):
                result_list: List[Any] = []
                for item in obj:  # type: ignore[misc]
                    result_list.append(substitute_env_vars(item))
                return result_list
            else:
                return obj

        return substitute_env_vars(config)

    def _parse_configuration(self, config: Dict[str, Any]) -> LLMConfiguration:
        """Parse the processed configuration into structured objects.

        Args:
            config: Processed configuration dictionary.

        Returns:
            Structured LLM configuration.

        Raises:
            InvalidConfigurationError: If configuration validation fails.
        """
        try:
            # Validate required fields
            if "default_provider" not in config:
                raise InvalidConfigurationError(
                    "Missing required field: default_provider"
                )

            if "providers" not in config:
                raise InvalidConfigurationError("Missing required field: providers")

            # Parse default provider
            try:
                default_provider = LLMProvider(config["default_provider"])
            except ValueError as e:
                raise InvalidConfigurationError(
                    f"Invalid default_provider: {config['default_provider']}"
                ) from e

            # Parse provider configurations
            providers: Dict[str, ProviderConfig] = {}

            for provider_name, provider_config in config["providers"].items():
                try:
                    provider_type = LLMProvider(provider_name)
                    providers[provider_name] = self._parse_provider_config(
                        provider_type, provider_config
                    )
                except ValueError as e:
                    raise InvalidConfigurationError(
                        f"Invalid provider name: {provider_name}"
                    ) from e

            # Validate that default provider exists and is enabled
            if default_provider.value not in providers:
                raise InvalidConfigurationError(
                    f"Default provider '{default_provider.value}' not found in providers"
                )

            if not providers[default_provider.value].enabled:
                raise InvalidConfigurationError(
                    f"Default provider '{default_provider.value}' is not enabled"
                )

            return LLMConfiguration(
                default_provider=default_provider, providers=providers
            )

        except Exception as e:
            if isinstance(e, InvalidConfigurationError):
                raise
            raise InvalidConfigurationError(f"Configuration parsing failed: {e}") from e

    def _parse_provider_config(
        self, provider_type: LLMProvider, config: Dict[str, Any]
    ) -> ProviderConfig:
        """Parse provider-specific configuration.

        Args:
            provider_type: Type of the provider.
            config: Provider configuration dictionary.

        Returns:
            Parsed provider configuration.
        """
        # Validate required base fields
        required_fields = ["enabled", "model"]
        for field in required_fields:
            if field not in config:
                raise InvalidConfigurationError(
                    f"Missing required field '{field}' for provider {provider_type.value}"
                )

        if provider_type == LLMProvider.AZURE_OPENAI:
            return AzureOpenAIConfig(
                enabled=config["enabled"],
                model=config["model"],
                max_tokens=config.get("max_tokens", 4096),
                temperature=config.get("temperature", 0.7),
                endpoint=config.get("endpoint", ""),
                api_key=config.get("api_key", ""),
                api_version=config.get("api_version", "2024-02-15-preview"),
                deployment_name=config.get("deployment_name", ""),
            )
        elif provider_type == LLMProvider.AWS_BEDROCK:
            return AWSBedrockConfig(
                enabled=config["enabled"],
                model=config["model"],
                max_tokens=config.get("max_tokens", 4096),
                temperature=config.get("temperature", 0.7),
                region=config.get("region", ""),
                access_key_id=config.get("access_key_id", ""),
                secret_access_key=config.get("secret_access_key", ""),
                session_token=config.get("session_token"),
            )
        else:
            raise InvalidConfigurationError(
                f"Unsupported provider type: {provider_type}"
            )
