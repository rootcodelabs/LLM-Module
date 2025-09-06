"""Azure OpenAI provider implementation."""

from typing import Any, Dict, List

import dspy  # type: ignore[import-untyped]

from .base import BaseLLMProvider
from ..exceptions import ProviderInitializationError


class AzureOpenAIProvider(BaseLLMProvider):
    """Azure OpenAI provider implementation using DSPY."""

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "Azure OpenAI"

    def get_required_config_fields(self) -> List[str]:
        """Return list of required configuration fields."""
        return [
            "enabled",
            "model",
            "endpoint",
            "api_key",
            "deployment_name",
            "api_version",
        ]

    def initialize(self) -> None:
        """Initialize the Azure OpenAI provider.

        Raises:
            ProviderInitializationError: If initialization fails.
        """
        try:
            self.validate_config()

            # Initialize DSPY Azure OpenAI client
            self._client = dspy.AzureOpenAI(  # type: ignore[attr-defined]
                api_base=self.config["endpoint"],
                api_key=self.config["api_key"],
                api_version=self.config["api_version"],
                model=self.config[
                    "deployment_name"
                ],  # DSPY uses deployment name as model
                max_tokens=self.config.get("max_tokens", 4096),
                temperature=self.config.get("temperature", 0.7),
            )

            self._initialized = True

        except Exception as e:
            raise ProviderInitializationError(
                f"Failed to initialize {self.provider_name} provider: {e}"
            ) from e

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate response from Azure OpenAI.

        Args:
            prompt: The input prompt for the LLM.
            **kwargs: Additional generation parameters.

        Returns:
            Generated response text.

        Raises:
            RuntimeError: If the provider is not initialized.
            Exception: If generation fails.
        """
        self._ensure_initialized()

        if self._client is None:
            raise RuntimeError("Client is not initialized")

        try:
            # Use DSPY's generate method
            response = self._client.generate(prompt, **kwargs)  # type: ignore[attr-defined]

            # DSPY returns a list of completions, we take the first one
            if isinstance(response, list) and len(response) > 0:  # type: ignore[arg-type]
                return response[0]  # type: ignore[return-value]
            elif isinstance(response, str):
                return response
            else:
                return str(response)  # type: ignore[arg-type]

        except Exception as e:
            raise RuntimeError(f"Failed to generate response: {e}") from e

    def get_dspy_client(self) -> dspy.LM:
        """Return DSPY-compatible client.

        Returns:
            DSPY LM client instance.

        Raises:
            RuntimeError: If the provider is not initialized.
        """
        self._ensure_initialized()

        if self._client is None:
            raise RuntimeError("Client is not initialized")

        return self._client

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the configured model.

        Returns:
            Dictionary containing model information.
        """
        base_info = super().get_model_info()
        base_info.update(
            {
                "endpoint": self.config.get("endpoint", ""),
                "deployment_name": self.config.get("deployment_name", ""),
                "api_version": self.config.get("api_version", ""),
            }
        )
        return base_info
