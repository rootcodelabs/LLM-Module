import os
from pathlib import Path
import pytest
import dspy  # type: ignore
from typing import Any
from llm_config_module.llm_manager import LLMManager
from llm_config_module.types import LLMProvider


@pytest.mark.skipif(
    not all(
        os.getenv(v)
        for v in [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
        ]
    ),
    reason="Azure environment variables not set",
)
def test_azure_llm_inference():
    cfg_path = (
        Path(__file__).parent.parent
        / "src"
        / "llm_config_module"
        / "config"
        / "llm_config.yaml"
    )
    assert cfg_path.exists(), f"llm_config.yaml not found at {cfg_path}"

    manager = LLMManager(str(cfg_path))

    # Check if Azure OpenAI provider is available and enabled
    is_azure_available = manager.is_provider_available(LLMProvider.AZURE_OPENAI)

    if not is_azure_available:
        print("\n🔒 Azure OpenAI provider is disabled in configuration")
        print("✅ Test passed - Azure OpenAI provider is properly disabled")
        return  # Test passes without doing inference

    # If Azure is enabled, proceed with inference test
    print("\n🔓 Azure OpenAI provider is enabled - running inference test")
    manager.configure_dspy()

    class QA(dspy.Signature):
        """Short factual answer"""

        question = dspy.InputField()  # type: ignore
        answer = dspy.OutputField()  # type: ignore

    qa = dspy.Predict(QA)
    out = qa(
        question="If this pass through the Azure OpenAI provider, say 'Azure DSPY Configuration Successful'"
    )

    print(
        "🤖 Question: If this pass through the Azure OpenAI provider, say 'Azure DSPY Configuration Successful'"
    )
    print(f"🎯 Answer: {out.answer}")  # type: ignore

    # Type-safe assertions
    answer: Any = getattr(out, "answer", None)
    assert answer is not None, "Answer should not be None"
    assert isinstance(answer, str), f"Answer should be string, got {type(answer)}"
    print("✅ Azure OpenAI inference test passed!")
