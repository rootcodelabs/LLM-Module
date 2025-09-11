import os
from pathlib import Path
import pytest
from typing import Dict, List

from llm_config_module.llm_manager import LLMManager
from llm_config_module.types import LLMProvider
from prompt_refiner_module.prompt_refiner import PromptRefinerAgent


class TestPromptRefinerAgent:
    """Test suite for PromptRefinerAgent functionality."""

    @pytest.fixture
    def config_path(self) -> str:
        """Get path to llm_config.yaml."""
        cfg_path = (
            Path(__file__).parent.parent
            / "src"
            / "llm_config_module"
            / "config"
            / "llm_config.yaml"
        )
        assert cfg_path.exists(), f"llm_config.yaml not found at {cfg_path}"
        return str(cfg_path)

    @pytest.fixture
    def sample_history(self) -> List[Dict[str, str]]:
        """Sample conversation history for testing."""
        return [
            {
                "role": "user",
                "content": "What government services are available for healthcare?",
            },
            {
                "role": "assistant",
                "content": "Government healthcare services include public hospitals, subsidized medical treatments, and health insurance programs like Medicaid and Medicare.",
            },
            {"role": "user", "content": "Can you provide more details about Medicaid?"},
        ]

    @pytest.fixture
    def empty_history(self) -> List[Dict[str, str]]:
        """Empty conversation history for testing."""
        return []

    def test_prompt_refiner_initialization_default(self, config_path: str) -> None:
        """Test PromptRefinerAgent initialization with default settings."""
        agent = PromptRefinerAgent(config_path=config_path)
        assert agent._default_n == 5  # type: ignore
        assert agent._manager is not None  # type: ignore
        assert agent._predictor is not None  # type: ignore

    def test_prompt_refiner_initialization_custom_n(self, config_path: str) -> None:
        """Test PromptRefinerAgent initialization with custom default_n."""
        agent = PromptRefinerAgent(config_path=config_path, default_n=3)
        assert agent._default_n == 3  # type: ignore

    def test_prompt_refiner_initialization_invalid_n(self, config_path: str) -> None:
        """Test PromptRefinerAgent initialization with invalid default_n."""
        with pytest.raises(ValueError, match="`default_n` must be a positive integer"):
            PromptRefinerAgent(config_path=config_path, default_n=0)

        with pytest.raises(ValueError, match="`default_n` must be a positive integer"):
            PromptRefinerAgent(config_path=config_path, default_n=-1)

    def test_validation_empty_question(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test validation with empty question."""
        agent = PromptRefinerAgent(config_path=config_path)

        with pytest.raises(ValueError, match="`question` must be a non-empty string"):
            agent.forward(sample_history, "", 3)

        with pytest.raises(ValueError, match="`question` must be a non-empty string"):
            agent.forward(sample_history, "   ", 3)

    def test_validation_invalid_n(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test validation with invalid n parameter."""
        agent = PromptRefinerAgent(config_path=config_path)

        with pytest.raises(ValueError, match="`n` must be a positive integer"):
            agent.forward(
                sample_history,
                "What are the benefits of government housing programs?",
                0,
            )

        with pytest.raises(ValueError, match="`n` must be a positive integer"):
            agent.forward(
                sample_history,
                "What are the benefits of government housing programs?",
                -1,
            )

    def test_validation_invalid_history(self, config_path: str) -> None:
        """Test validation with invalid history format."""
        agent = PromptRefinerAgent(config_path=config_path)

        with pytest.raises(
            ValueError, match="`history` must be a dspy.History or a sequence"
        ):
            agent.forward("invalid_history", "What is AI?", 3)  # type: ignore

        with pytest.raises(
            ValueError, match="`history` must be a dspy.History or a sequence"
        ):
            agent.forward({"invalid": "format"}, "What is AI?", 3)  # type: ignore

    @pytest.mark.skipif(
        not any(
            os.getenv(var) for var in ["AWS_ACCESS_KEY_ID", "AZURE_OPENAI_API_KEY"]
        ),
        reason="No LLM provider environment variables set",
    )
    def test_prompt_refiner_with_history(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner with conversation history."""
        manager = LLMManager(config_path)

        # Find available provider
        available_providers = manager.get_available_providers()
        if not available_providers:
            pytest.skip("No LLM providers available for testing")

        provider = next(iter(available_providers.keys()))
        print(f"\n🔧 Testing with provider: {provider.value}")

        agent = PromptRefinerAgent(
            config_path=config_path, provider=provider, default_n=3
        )

        question = "How can I apply for unemployment benefits?"
        rewrites = agent.forward(sample_history, question, n=3)

        # Validate output
        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) <= 3, "Should return at most 3 rewrites"
        assert len(rewrites) > 0, "Should return at least 1 rewrite"

        for rewrite in rewrites:
            assert isinstance(rewrite, str), "Each rewrite should be a string"
            assert len(rewrite.strip()) > 0, "Each rewrite should be non-empty"

        print(f"🤖 Original question: {question}")
        print(f"📝 Generated {len(rewrites)} rewrites:")
        for i, rewrite in enumerate(rewrites, 1):
            print(f"  {i}. {rewrite}")

    @pytest.mark.skipif(
        not any(
            os.getenv(var) for var in ["AWS_ACCESS_KEY_ID", "AZURE_OPENAI_API_KEY"]
        ),
        reason="No LLM provider environment variables set",
    )
    def test_prompt_refiner_without_history(
        self, config_path: str, empty_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner without conversation history."""
        manager = LLMManager(config_path)

        # Find available provider
        available_providers = manager.get_available_providers()
        if not available_providers:
            pytest.skip("No LLM providers available for testing")

        provider = next(iter(available_providers.keys()))

        agent = PromptRefinerAgent(
            config_path=config_path, provider=provider, default_n=2
        )

        question = "What are the eligibility criteria for food assistance programs?"
        rewrites = agent.forward(empty_history, question, n=2)

        # Validate output
        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) <= 2, "Should return at most 2 rewrites"
        assert len(rewrites) > 0, "Should return at least 1 rewrite"

        for rewrite in rewrites:
            assert isinstance(rewrite, str), "Each rewrite should be a string"
            assert len(rewrite.strip()) > 0, "Each rewrite should be non-empty"

        print(f"🤖 Original question: {question}")
        print(f"📝 Generated {len(rewrites)} rewrites (no history):")
        for i, rewrite in enumerate(rewrites, 1):
            print(f"  {i}. {rewrite}")

    @pytest.mark.skipif(
        not any(
            os.getenv(var) for var in ["AWS_ACCESS_KEY_ID", "AZURE_OPENAI_API_KEY"]
        ),
        reason="No LLM provider environment variables set",
    )
    def test_prompt_refiner_default_n(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner using default n value."""
        manager = LLMManager(config_path)

        # Find available provider
        available_providers = manager.get_available_providers()
        if not available_providers:
            pytest.skip("No LLM providers available for testing")

        provider = next(iter(available_providers.keys()))

        agent = PromptRefinerAgent(
            config_path=config_path, provider=provider, default_n=4
        )

        question = "How does this technology impact society?"
        # Don't specify n, should use default_n=4
        rewrites = agent.forward(sample_history, question)

        # Validate output
        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) <= 4, "Should return at most 4 rewrites (default_n)"
        assert len(rewrites) > 0, "Should return at least 1 rewrite"

        print(f"🤖 Original question: {question}")
        print(f"📝 Generated {len(rewrites)} rewrites (using default_n=4):")
        for i, rewrite in enumerate(rewrites, 1):
            print(f"  {i}. {rewrite}")

    @pytest.mark.skipif(
        not any(
            os.getenv(var) for var in ["AWS_ACCESS_KEY_ID", "AZURE_OPENAI_API_KEY"]
        ),
        reason="No LLM provider environment variables set",
    )
    def test_prompt_refiner_single_rewrite(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner with n=1."""
        manager = LLMManager(config_path)

        # Find available provider
        available_providers = manager.get_available_providers()
        if not available_providers:
            pytest.skip("No LLM providers available for testing")

        provider = next(iter(available_providers.keys()))

        agent = PromptRefinerAgent(config_path=config_path, provider=provider)

        question = "Tell me about deep learning."
        rewrites = agent.forward(sample_history, question, n=1)

        # Validate output
        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) == 1, "Should return exactly 1 rewrite"
        assert isinstance(rewrites[0], str), "Rewrite should be a string"
        assert len(rewrites[0].strip()) > 0, "Rewrite should be non-empty"

        print(f"🤖 Original question: {question}")
        print(f"📝 Single rewrite: {rewrites[0]}")

    def test_prompt_refiner_with_specific_provider_aws(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner with specific AWS provider."""
        if not all(
            os.getenv(v)
            for v in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]
        ):
            pytest.skip("AWS environment variables not set")

        manager = LLMManager(config_path)
        if not manager.is_provider_available(LLMProvider.AWS_BEDROCK):
            pytest.skip("AWS Bedrock provider not available")

        agent = PromptRefinerAgent(
            config_path=config_path, provider=LLMProvider.AWS_BEDROCK, default_n=2
        )

        question = "What are neural networks?"
        rewrites = agent.forward(sample_history, question, n=2)

        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) <= 2, "Should return at most 2 rewrites"
        assert len(rewrites) > 0, "Should return at least 1 rewrite"

        print(f"🤖 AWS Bedrock - Original: {question}")
        print(f"📝 AWS Bedrock - Rewrites: {rewrites}")

    def test_prompt_refiner_with_specific_provider_azure(
        self, config_path: str, sample_history: List[Dict[str, str]]
    ) -> None:
        """Test prompt refiner with specific Azure provider."""
        if not all(
            os.getenv(v)
            for v in [
                "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT_NAME",
            ]
        ):
            pytest.skip("Azure environment variables not set")

        manager = LLMManager(config_path)
        if not manager.is_provider_available(LLMProvider.AZURE_OPENAI):
            pytest.skip("Azure OpenAI provider not available")

        agent = PromptRefinerAgent(
            config_path=config_path, provider=LLMProvider.AZURE_OPENAI, default_n=3
        )

        question = "Explain computer vision applications."
        rewrites = agent.forward(sample_history, question, n=3)

        assert isinstance(rewrites, list), "Output should be a list"
        assert len(rewrites) <= 3, "Should return at most 3 rewrites"
        assert len(rewrites) > 0, "Should return at least 1 rewrite"

        print(f"🤖 Azure OpenAI - Original: {question}")
        print(f"📝 Azure OpenAI - Rewrites: {rewrites}")
