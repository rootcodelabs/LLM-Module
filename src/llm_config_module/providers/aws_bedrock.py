"""AWS Bedrock provider implementation."""

from typing import Any, Dict, List

import dspy  # type: ignore[import-untyped]

from .base import BaseLLMProvider
from ..exceptions import ProviderInitializationError


class AWSBedrockProvider(BaseLLMProvider):
    """AWS Bedrock provider implementation using DSPY."""

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "AWS Bedrock"

    def get_required_config_fields(self) -> List[str]:
        """Return list of required configuration fields."""
        return ["enabled", "model", "region", "access_key_id", "secret_access_key"]

    def initialize(self) -> None:
        """Initialize the AWS Bedrock provider.

        Raises:
            ProviderInitializationError: If initialization fails.
        """
        try:
            self.validate_config()

            # Prepare AWS credentials
            aws_config = {
                "region_name": self.config["region"],
                "aws_access_key_id": self.config["access_key_id"],
                "aws_secret_access_key": self.config["secret_access_key"],
            }

            # Add session token if provided
            if self.config.get("session_token"):
                aws_config["aws_session_token"] = self.config["session_token"]

            # Initialize DSPY Bedrock client
            # Note: DSPY may use different parameter names, this is based on common patterns
            self._client = dspy.Bedrock(  # type: ignore[attr-defined]
                model=self.config["model"],
                max_tokens=self.config.get("max_tokens", 4096),
                temperature=self.config.get("temperature", 0.7),
                **aws_config,
            )

            self._initialized = True

        except Exception as e:
            raise ProviderInitializationError(
                f"Failed to initialize {self.provider_name} provider: {e}"
            ) from e

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate response from AWS Bedrock.

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
                "region": self.config.get("region", ""),
                "model_id": self.config.get("model", ""),
            }
        )
        return base_info
