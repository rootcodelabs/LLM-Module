"""
Test that required Azure environment variables are set.

This ensures that the environment is properly configured before the LLM orchestration service runs.
"""

import os
import pytest
from loguru import logger


@pytest.mark.env
def test_azure_env_vars_present() -> None:
    """
    Validate that AZURE_MODEL_API_KEY and AZURE_MODEL_ENDPOINT are set and non-empty,
    and log masked versions (first 3 characters only).
    """
    api_key = os.getenv("AZURE_MODEL_API_KEY")
    endpoint = os.getenv("AZURE_MODEL_ENDPOINT")

    assert api_key is not None, "AZURE_MODEL_API_KEY is not set in environment!"
    assert api_key.strip() != "", "AZURE_MODEL_API_KEY is empty!"

    assert endpoint is not None, "AZURE_MODEL_ENDPOINT is not set in environment!"
    assert endpoint.strip() != "", "AZURE_MODEL_ENDPOINT is empty!"

    # Masked display: show only first 3 characters
    masked_api_key = api_key[:3] + "..." if len(api_key) >= 3 else "***"
    masked_endpoint = endpoint[:3] + "..." if len(endpoint) >= 3 else "***"

    logger.info(f"✅ AZURE_MODEL_API_KEY is set: {masked_api_key}")
    logger.info(f"✅ AZURE_MODEL_ENDPOINT is set: {masked_endpoint}")
