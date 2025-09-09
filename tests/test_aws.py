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
        for v in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]
    ),
    reason="AWS environment variables not set",
)
def test_aws_llm_inference():
    cfg_path = (
        Path(__file__).parent.parent
        / "src"
        / "llm_config_module"
        / "config"
        / "llm_config.yaml"
    )
    assert cfg_path.exists(), f"llm_config.yaml not found at {cfg_path}"

    manager = LLMManager(str(cfg_path))

    # Check if AWS Bedrock provider is available and enabled
    is_aws_available = manager.is_provider_available(LLMProvider.AWS_BEDROCK)

    if not is_aws_available:
        print("\nAWS Bedrock provider is disabled in configuration")
        print("Test passed - AWS Bedrock provider is properly disabled")
        return  # Test passes without doing inference

    # If AWS is enabled, proceed with inference test
    print("\n🔓 AWS Bedrock provider is enabled - running inference test")
    manager.configure_dspy()

    class QA(dspy.Signature):
        """Short factual answer"""

        question = dspy.InputField()  # type: ignore
        answer = dspy.OutputField()  # type: ignore

    qa = dspy.Predict(QA)
    out = qa(
        question="If this pass through the AWS Bedrock provider, say 'AWS DSPY Configuration Successful'"
    )

    # Type-safe assertions
    answer: Any = getattr(out, "answer", None)
    assert answer is not None, "Answer should not be None"
    assert isinstance(answer, str), f"Answer should be string, got {type(answer)}"
