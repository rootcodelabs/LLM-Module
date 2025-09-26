import os
import pytest

def test_azure_env_vars_present():
    """
    Test that AZURE_MODEL_API_KEY and AZURE_MODEL_ENDPOINT are set in the environment.
    """
    assert "AZURE_MODEL_API_KEY" in os.environ, "AZURE_MODEL_API_KEY is not set in environment!"
    assert os.environ["AZURE_MODEL_API_KEY"], "AZURE_MODEL_API_KEY is empty!"
    assert "AZURE_MODEL_ENDPOINT" in os.environ, "AZURE_MODEL_ENDPOINT is not set in environment!"
    assert os.environ["AZURE_MODEL_ENDPOINT"], "AZURE_MODEL_ENDPOINT is empty!"
    # Optionally log presence (not value)
    print("AZURE_MODEL_API_KEY and AZURE_MODEL_ENDPOINT are present in environment.")
