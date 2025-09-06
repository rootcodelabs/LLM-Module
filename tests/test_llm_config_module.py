"""Tests for the LLM Config Module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_config_module import (
    LLMManager,
    LLMProvider,
    ConfigurationError
)
from llm_config_module.config.loader import ConfigurationLoader
from llm_config_module.factory import LLMFactory


class TestConfigurationLoader:
    """Test the configuration loader."""

    def test_environment_variable_substitution(self) -> None:
        """Test environment variable substitution in configuration."""
        config_content = """
llm:
  default_provider: "azure_openai"
  providers:
    azure_openai:
      enabled: true
      model: "gpt-4o"
      endpoint: "${TEST_ENDPOINT:https://test.openai.azure.com}"
      api_key: "${TEST_API_KEY}"
      deployment_name: "${TEST_DEPLOYMENT:test-deployment}"
      api_version: "2024-02-15-preview"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {
                    "TEST_ENDPOINT": "https://custom.openai.azure.com",
                    "TEST_API_KEY": "test-key-123",
                },
            ):
                loader = ConfigurationLoader(config_path)
                config = loader.load_config()

                azure_config = config.get_provider_config(LLMProvider.AZURE_OPENAI)
                assert azure_config is not None
                assert (
                    azure_config.to_dict()["endpoint"]
                    == "https://custom.openai.azure.com"
                )
                assert azure_config.to_dict()["api_key"] == "test-key-123"
                assert (
                    azure_config.to_dict()["deployment_name"] == "test-deployment"
                )  # default value
        finally:
            os.unlink(config_path)

    def test_invalid_configuration_missing_section(self) -> None:
        """Test handling of invalid configuration missing llm section."""
        config_content = """
invalid:
  key: value
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            loader = ConfigurationLoader(config_path)
            with pytest.raises(ConfigurationError, match="missing 'llm' section"):
                loader.load_config()
        finally:
            os.unlink(config_path)


class TestLLMFactory:
    """Test the LLM factory."""

    def test_unsupported_provider(self) -> None:
        """Test handling of unsupported provider."""
        # Create a mock provider type that doesn't exist
        with pytest.raises(ValueError):
            # This should fail when trying to create the enum
            LLMProvider("unsupported_provider")

    def test_supported_providers(self) -> None:
        """Test getting supported providers."""
        supported = LLMFactory.get_supported_providers()
        assert LLMProvider.AZURE_OPENAI in supported
        assert LLMProvider.AWS_BEDROCK in supported

    def test_provider_registration(self) -> None:
        """Test provider registration functionality."""

        # Test that we can register a new provider
        original_providers = LLMFactory.get_supported_providers().copy()

        # Note: We can't actually test this without extending the enum
        # This is more of a design verification
        assert len(original_providers) == 2  # Azure OpenAI and AWS Bedrock


class TestLLMManager:
    """Test the LLM Manager."""

    def test_singleton_behavior(self) -> None:
        """Test that LLMManager follows singleton pattern."""
        # Reset singleton for clean test
        LLMManager.reset_instance()

        manager1 = LLMManager()
        manager2 = LLMManager()

        assert manager1 is manager2

    def test_configuration_loading_failure(self) -> None:
        """Test handling of configuration loading failure."""
        LLMManager.reset_instance()

        # Try to load from non-existent file
        with pytest.raises(ConfigurationError):
            LLMManager("/non/existent/path.yaml")

    def test_provider_availability_check(self) -> None:
        """Test provider availability checking."""
        config_content = """
llm:
  default_provider: "azure_openai"
  providers:
    azure_openai:
      enabled: true
      model: "gpt-4o"
      endpoint: "https://test.openai.azure.com"
      api_key: "test-key"
      deployment_name: "test-deployment"
      api_version: "2024-02-15-preview"
    aws_bedrock:
      enabled: false
      model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
      region: "us-east-1"
      access_key_id: "test-key"
      secret_access_key: "test-secret"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            config_path = f.name

        try:
            LLMManager.reset_instance()

            # Mock the DSPY initialization to avoid actual API calls
            with patch("llm_config_module.providers.azure_openai.dspy.AzureOpenAI"):
                manager = LLMManager(config_path)

                # Azure OpenAI should be available (enabled)
                assert manager.is_provider_available(LLMProvider.AZURE_OPENAI)

                # AWS Bedrock should not be available (disabled)
                assert not manager.is_provider_available(LLMProvider.AWS_BEDROCK)

                # Should be able to get available providers
                available = manager.get_available_providers()
                assert LLMProvider.AZURE_OPENAI in available
                assert LLMProvider.AWS_BEDROCK not in available
        finally:
            os.unlink(config_path)


def test_module_imports() -> None:
    """Test that all expected classes can be imported from the module."""
    from llm_config_module import (
        LLMManager,
        LLMFactory,
        LLMProvider,
        ConfigurationError,
        BaseLLMProvider,
        AzureOpenAIProvider,
        AWSBedrockProvider,
    )

    # Verify classes exist and are importable
    assert LLMManager is not None
    assert LLMFactory is not None
    assert LLMProvider is not None
    assert ConfigurationError is not None
    assert BaseLLMProvider is not None
    assert AzureOpenAIProvider is not None
    assert AWSBedrockProvider is not None


def test_provider_enum_values() -> None:
    """Test that provider enum has expected values."""
    assert LLMProvider.AZURE_OPENAI.value == "azure_openai"
    assert LLMProvider.AWS_BEDROCK.value == "aws_bedrock"

    # Test that we can create providers from string values
    assert LLMProvider("azure_openai") == LLMProvider.AZURE_OPENAI
    assert LLMProvider("aws_bedrock") == LLMProvider.AWS_BEDROCK
