"""Test LLM Config Module integration with Vault."""

import pytest
from pathlib import Path
from llm_config_module.llm_manager import LLMManager
from llm_config_module.exceptions import ConfigurationError


def check_vault_available():
    """Check if vault is available."""
    try:
        from src.rag_config_manager.vault.client import VaultClient

        vault = VaultClient()
        return vault.is_vault_available()
    except Exception:
        return False


@pytest.mark.skipif(not check_vault_available(), reason="Vault is not available")
class TestVaultIntegration:
    """Test suite for vault integration."""

    def setup_method(self):
        """Setup for each test method."""
        # Reset the singleton instance to ensure each test gets a fresh instance
        LLMManager.reset_instance()

        self.cfg_path = (
            Path(__file__).parent.parent
            / "src"
            / "llm_config_module"
            / "config"
            / "llm_config.yaml"
        )
        assert self.cfg_path.exists(), f"llm_config.yaml not found at {self.cfg_path}"

    def test_production_environment_initialization(self):
        """Test that production environment initializes correctly."""
        try:
            manager = LLMManager(
                config_path=str(self.cfg_path), environment="production"
            )

            # Should not raise exception if vault has production connections
            providers = manager.get_available_providers()
            assert isinstance(providers, dict)
            print(
                f"Production environment initialized with providers: {list(providers.keys())}"
            )

        except ConfigurationError as e:
            if "No production connection found" in str(e):
                pytest.skip("No production connections configured in vault")
            else:
                raise

    def test_development_environment_requires_connection_id(self):
        """Test that development environment requires connection_id."""
        with pytest.raises(ConfigurationError, match="connection_id is required"):
            LLMManager(
                config_path=str(self.cfg_path),
                environment="development",
                # Missing connection_id parameter
            )

    def test_invalid_connection_id_fails(self):
        """Test that invalid connection_id causes failure."""
        with pytest.raises(ConfigurationError):
            LLMManager(
                config_path=str(self.cfg_path),
                environment="development",
                connection_id="invalid-connection-id-12345",
            )

    def test_vault_configuration_loaded(self):
        """Test that vault configuration is properly loaded."""
        try:
            manager = LLMManager(
                config_path=str(self.cfg_path), environment="production"
            )

            # Access the configuration through public method
            config = manager.get_configuration()
            assert config is not None, "Configuration should be loaded"
            assert config.vault is not None, "Vault configuration should be loaded"
            assert config.vault.enabled is True, "Vault should be enabled"
            assert config.vault.url is not None, "Vault URL should be configured"
            assert config.vault.url != "", "Vault URL should not be empty"

            print("Vault configuration properly loaded")

        except ConfigurationError as e:
            if "No production connection found" in str(e):
                pytest.skip("No production connections configured in vault")
            else:
                raise

    def test_environment_variable_substitution_in_vault_config(self):
        """Test that environment variables in vault config are properly substituted."""
        import os

        # Ensure vault env vars are set
        vault_addr = os.getenv("VAULT_ADDR")
        vault_token = os.getenv("VAULT_TOKEN")

        if not vault_addr or not vault_token:
            pytest.skip("VAULT_ADDR and VAULT_TOKEN environment variables must be set")

        try:
            manager = LLMManager(
                config_path=str(self.cfg_path), environment="production"
            )

            config = manager.get_configuration()
            assert config is not None, "Configuration should be loaded"
            assert config.vault is not None, "Vault configuration should be loaded"
            assert config.vault.url == vault_addr, (
                f"Expected vault URL {vault_addr}, got {config.vault.url}"
            )
            # Note: token might be masked in config for security

            print("Environment variable substitution working")

        except ConfigurationError as e:
            if "No production connection found" in str(e):
                pytest.skip("No production connections configured in vault")
            else:
                raise


@pytest.mark.skipif(
    check_vault_available(), reason="Vault is available, skipping fallback tests"
)
def test_vault_unavailable_fallback():
    """Test behavior when vault is unavailable."""
    cfg_path = (
        Path(__file__).parent.parent
        / "src"
        / "llm_config_module"
        / "config"
        / "llm_config.yaml"
    )

    # This should fail since we removed environment variable support
    with pytest.raises(ConfigurationError, match="Failed to resolve secrets"):
        LLMManager(config_path=str(cfg_path), environment="production")

    print("System properly fails when vault unavailable (as expected)")
