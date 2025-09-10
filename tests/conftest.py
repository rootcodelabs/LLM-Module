"""Pytest configuration and fixtures."""

import sys
import os
import pytest
from pathlib import Path
from typing import Dict, Generator
from testcontainers.vault import VaultContainer  # type: ignore
from loguru import logger
import hvac  # type: ignore


# Add src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def vault_container() -> Generator[VaultContainer, None, None]:
    """Create a Vault container for testing."""
    with VaultContainer() as vault:
        # Vault container is automatically ready when context manager exits
        yield vault


@pytest.fixture(scope="session")
def vault_client(vault_container: VaultContainer) -> hvac.Client:
    """Get the Vault client."""

    # Get the vault URL from the container
    vault_url = vault_container.get_connection_url()

    # Create hvac client with the correct root token
    client = hvac.Client(url=vault_url, token=vault_container.root_token)  # type: ignore
    return client


@pytest.fixture(scope="session")
def populated_vault(vault_client: hvac.Client) -> None:
    """Populate vault with test data using proper provider-specific paths and Connection model structure."""
    from datetime import datetime

    # Create test data with proper Connection model structure
    test_data = {
        "users/testuser/aws_bedrock/credentials": {
            "metadata": {
                "id": "conn_aws_prod_01",
                "name": "AWS Bedrock Production",
                "description": "Production AWS Bedrock connection",
                "provider": "aws_bedrock",
                "environment": "production",
                "created_by": "testuser",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_used": None,
                "usage_count": 0,
                "tags": ["production", "aws"],
                "is_active": True,
                "is_default": False,
            },
            "connection_data": {
                "region": "us-east-1",
                "access_key_id": "AKIA...",
                "secret_access_key": "test-secret-key",
                "session_token": None,
            },
        },
        "users/testuser/azure_openai/credentials": {
            "metadata": {
                "id": "conn_azure_prod_01",
                "name": "Azure OpenAI Production",
                "description": "Production Azure OpenAI connection",
                "provider": "azure_openai",
                "environment": "production",
                "created_by": "testuser",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_used": None,
                "usage_count": 0,
                "tags": ["production", "azure"],
                "is_active": True,
                "is_default": False,
            },
            "connection_data": {
                "endpoint": "https://test.openai.azure.com/",
                "api_key": "test-azure-api-key",
                "deployment_name": "gpt-4",
                "api_version": "2025-01-01-preview",
            },
        },
    }

    # Populate vault with test data
    for path, data in test_data.items():
        try:
            vault_client.secrets.kv.v2.create_or_update_secret(  # type: ignore
                path=path, secret=data
            )
            logger.debug(f"Created test secret at {path}")
        except Exception as e:
            logger.error(f"Failed to create secret at {path}: {e}")
            raise


@pytest.fixture
def vault_env_vars(
    vault_container: VaultContainer, populated_vault: None
) -> Generator[Dict[str, str], None, None]:
    """Set up environment variables for Vault connection."""
    env_vars: Dict[str, str] = {
        "VAULT_ADDR": vault_container.get_connection_url(),  # type: ignore  # Use VAULT_ADDR to match config
        "VAULT_URL": vault_container.get_connection_url(),  # type: ignore  # Also set VAULT_URL for compatibility
        "VAULT_TOKEN": vault_container.root_token,  # type: ignore
        "ENVIRONMENT": "production",
    }

    # Set environment variables
    for key, value in env_vars.items():
        os.environ[key] = value

    yield env_vars

    # Clean up environment variables
    for key in env_vars.keys():
        os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Reset singleton instances between tests."""
    # Reset LLMManager singleton
    from llm_config_module.llm_manager import LLMManager

    if hasattr(LLMManager, "_instance"):
        LLMManager._instance = None  # type: ignore  # Intentional protected access for testing

    # Reset VaultConnectionManager singleton - with error handling for missing class
    try:
        from rag_config_manager.vault.connection_manager import VaultConnectionManager  # type: ignore

        if hasattr(VaultConnectionManager, "_instance"):  # type: ignore
            VaultConnectionManager._instance = None  # type: ignore  # Intentional protected access for testing
    except ImportError:
        # VaultConnectionManager might not be available in all test contexts
        pass

    yield

    # Clean up after test
    if hasattr(LLMManager, "_instance"):
        LLMManager._instance = None  # type: ignore  # Intentional protected access for testing
    try:
        from rag_config_manager.vault.connection_manager import VaultConnectionManager  # type: ignore

        if hasattr(VaultConnectionManager, "_instance"):  # type: ignore
            VaultConnectionManager._instance = None  # type: ignore  # Intentional protected access for testing
    except ImportError:
        pass
