"""Helper functions for vault-based testing."""

from typing import List
from pathlib import Path


def check_vault_available() -> bool:
    """Check if vault is available for testing."""
    try:
        from src.rag_config_manager.vault.client import VaultClient

        vault = VaultClient()
        return vault.is_vault_available()
    except Exception:
        return False


def get_available_providers_from_vault() -> List[str]:
    """Get list of available providers from vault for production environment.

    Returns:
        List of provider names that are available in vault for production
    """
    try:
        from src.llm_config_module.llm_manager import LLMManager

        cfg_path = (
            Path(__file__).parent.parent
            / "src"
            / "llm_config_module"
            / "config"
            / "llm_config.yaml"
        )

        # Reset singleton to ensure fresh discovery
        LLMManager.reset_instance()

        # Try to create manager with production environment
        manager = LLMManager(str(cfg_path), environment="production")

        # Get available providers
        providers = manager.get_available_providers()
        return list(providers.keys())

    except Exception as e:
        print(f"Failed to get providers from vault: {e}")
        return []


def should_skip_aws_test() -> bool:
    """Determine if AWS test should be skipped.

    Returns:
        True if AWS test should be skipped (vault not available or AWS not in vault)
    """
    if not check_vault_available():
        return True

    available_providers = get_available_providers_from_vault()
    return "aws_bedrock" not in available_providers


def should_skip_azure_test() -> bool:
    """Determine if Azure test should be skipped.

    Returns:
        True if Azure test should be skipped (vault not available or Azure not in vault)
    """
    if not check_vault_available():
        return True

    available_providers = get_available_providers_from_vault()
    return "azure_openai" not in available_providers
