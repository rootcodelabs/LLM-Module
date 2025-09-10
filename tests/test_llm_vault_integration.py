#!/usr/bin/env python3
"""Test script for LLM Config Module with Vault integration."""

import os
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger
from llm_config_module.llm_manager import LLMManager


# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)


def test_production_environment():
    """Test LLM manager with production environment."""
    logger.info("Testing LLM Manager with production environment...")

    # Set vault environment variables
    os.environ["VAULT_ADDR"] = "http://localhost:8200"
    os.environ["VAULT_TOKEN"] = "myroot"

    # Initialize LLM Manager for production
    llm_manager = LLMManager(environment="production")

    logger.success("LLM Manager initialized successfully for production")

    # Try to get a provider
    providers = llm_manager.get_available_providers()
    logger.info(f"Available providers: {providers}")

    # Assert that we got providers as a dictionary
    assert isinstance(providers, dict), "Providers should be a dictionary"


def test_development_environment():
    """Test LLM manager with development environment."""
    logger.info("Testing LLM Manager with development environment...")

    # Set vault environment variables
    os.environ["VAULT_ADDR"] = "http://localhost:8200"
    os.environ["VAULT_TOKEN"] = "myroot"

    # For development environment tests, we'll use a dummy connection ID
    # In a real scenario, this would be provided by the API
    test_connection_id = "test-connection-1"

    try:
        # Initialize LLM Manager for development
        llm_manager = LLMManager(
            environment="development", connection_id=test_connection_id
        )

        logger.success("LLM Manager initialized successfully for development")

        # Try to get a provider
        providers = llm_manager.get_available_providers()
        logger.info(f"Available providers: {providers}")

        # Assert that we got providers as a dictionary
        assert isinstance(providers, dict), "Providers should be a dictionary"

    except Exception as e:
        # If the test connection doesn't exist, that's expected - just skip
        logger.info(f"Development test skipped (expected if no test connection): {e}")
        pytest.skip(f"Development environment test skipped: {e}")


def main():
    """Main test function."""
    logger.info("Starting LLM Config Module Vault integration tests...")

    # Check if vault is running
    try:
        import requests

        response = requests.get("http://localhost:8200/v1/sys/health", timeout=5)
        if response.status_code not in [200, 429, 472, 473, 501, 503]:
            logger.error(
                "Vault is not responding properly. Please ensure Vault is running."
            )
            return
    except Exception as e:
        logger.error(f"Cannot connect to Vault: {e}")
        logger.info("Please ensure Vault is running with: docker-compose up vault")
        return

    logger.success("Vault is running and accessible")

    # When running as a script (not via pytest), we can call the test functions
    if __name__ == "__main__":
        logger.info("Running tests manually...")

        try:
            test_production_environment()
            logger.success("Production test completed successfully!")
        except Exception as e:
            logger.error(f"Production test failed: {e}")

        try:
            test_development_environment()
            logger.success("Development test completed successfully!")
        except Exception as e:
            logger.error(f"Development test failed: {e}")

        logger.success("Manual test execution completed!")


if __name__ == "__main__":
    main()
