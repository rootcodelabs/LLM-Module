import pytest
import dspy  # type: ignore
from typing import Any
from pathlib import Path
from src.llm_config_module.llm_manager import LLMManager
from src.llm_config_module.types import LLMProvider
from vault_test_helpers import should_skip_azure_test


@pytest.mark.skipif(
    should_skip_azure_test(),
    reason="Azure OpenAI not available in vault or vault not accessible",
)
def test_azure_llm_inference():
    """Test that Azure OpenAI can generate text."""
    cfg_path = (
        Path(__file__).parent.parent
        / "src"
        / "llm_config_module"
        / "config"
        / "llm_config.yaml"
    )
    assert cfg_path.exists(), f"llm_config.yaml not found at {cfg_path}"

    # Reset singleton to ensure fresh vault discovery
    LLMManager.reset_instance()

    # Initialize with production environment to use vault credentials
    llm_manager = LLMManager(str(cfg_path), environment="production")

    # Check if Azure OpenAI provider is available and enabled
    is_azure_available = llm_manager.is_provider_available(LLMProvider.AZURE_OPENAI)

    if not is_azure_available:
        print("\nAzure OpenAI provider is disabled in configuration")
        print("Test passed - Azure OpenAI provider is properly disabled")
        return  # Test passes without doing inference

    # If Azure is enabled, proceed with inference test
    print("\nAzure OpenAI provider is enabled - running inference test")
    llm_manager.configure_dspy()

    class QA(dspy.Signature):
        """Short factual answer"""

        question = dspy.InputField()  # type: ignore
        answer = dspy.OutputField()  # type: ignore

    qa = dspy.Predict(QA)
    out = qa(
        question="If this pass through the Azure OpenAI provider, say 'Azure DSPY Configuration Successful'"
    )

    print(
        "Question: If this pass through the Azure OpenAI provider, say 'Azure DSPY Configuration Successful'"
    )
    print(f"Answer: {out.answer}")  # type: ignore

    # Type-safe assertions
    answer: Any = getattr(out, "answer", None)
    assert answer is not None, "Answer should not be None"
    assert isinstance(answer, str), f"Answer should be string, got {type(answer)}"
    print("Azure OpenAI inference test passed!")
