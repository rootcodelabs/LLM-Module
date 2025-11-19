"""
Improved Custom LLM adapter for NeMo Guardrails using DSPy.
Follows NeMo's official custom LLM provider pattern using LangChain's BaseLanguageModel.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union, cast, Iterator, AsyncIterator
import asyncio
import dspy
from loguru import logger

from langchain_core.callbacks.manager import (
    CallbackManagerForLLMRun,
    AsyncCallbackManagerForLLMRun,
)
from langchain_core.outputs import LLMResult, Generation
from langchain_core.language_models.llms import LLM
from src.guardrails.guardrails_llm_configs import TEMPERATURE, MAX_TOKENS, MODEL_NAME


class DSPyNeMoLLM(LLM):
    """
    Production-ready custom LLM provider for NeMo Guardrails using DSPy with streaming support.

    This adapter follows NeMo's official pattern for custom LLM providers by:
    1. Inheriting from LangChain's LLM base class
    2. Implementing required methods: _call, _llm_type
    3. Implementing async methods: _acall (REQUIRED by NeMo Guardrails validation)
    4. Implementing streaming methods: _stream, _astream
    5. Using DSPy's configured LM for actual generation
    6. Proper error handling and logging

    Streaming Implementation:
    - Yields string tokens (not Generation objects)
    - Splits response into word-level chunks
    - Compatible with NeMo Guardrails buffering and validation
    """

    model_name: str = MODEL_NAME
    temperature: float = TEMPERATURE
    max_tokens: int = MAX_TOKENS
    streaming: bool = True

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the DSPy NeMo LLM adapter with streaming support."""
        super().__init__(**kwargs)
        logger.info(
            f"Initialized DSPyNeMoLLM adapter with streaming support "
            f"(model={self.model_name}, temp={self.temperature}, max_tokens={self.max_tokens})"
        )

    @property
    def _llm_type(self) -> str:
        """Return identifier for LLM type (required by LangChain)."""
        return "dspy-custom"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return identifying parameters for the LLM."""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "streaming": self.streaming,
        }

    def _get_dspy_lm(self) -> Any:
        """
        Get the active DSPy LM from settings.

        Returns:
            Active DSPy LM instance

        Raises:
            RuntimeError: If no DSPy LM is configured
        """
        lm = dspy.settings.lm
        if lm is None:
            raise RuntimeError(
                "No DSPy LM configured. Please configure dspy.settings.lm first."
            )
        return lm

    def _extract_text_from_response(self, response: Union[str, List[Any], Any]) -> str:
        """
        Extract text from various DSPy response formats.

        Args:
            response: Response from DSPy LM

        Returns:
            Extracted text string
        """
        if isinstance(response, str):
            return response.strip()

        if isinstance(response, list) and len(cast(List[Any], response)) > 0:
            return str(cast(List[Any], response)[0]).strip()

        if not isinstance(response, list):
            return str(response).strip()
        return ""

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        Synchronous call method (required by LangChain).

        Args:
            prompt: The prompt string to generate from
            stop: Optional stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Returns:
            Generated text response

        Raises:
            RuntimeError: If DSPy LM is not configured
            Exception: For other generation errors
        """
        try:
            lm = self._get_dspy_lm()
            logger.debug(f"DSPyNeMoLLM._call: prompt length={len(prompt)}")

            response = lm(prompt)
            result = self._extract_text_from_response(response)

            logger.debug(f"DSPyNeMoLLM._call: result length={len(result)}")
            return result

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Error in DSPyNeMoLLM._call: {str(e)}")
            raise RuntimeError(f"LLM generation failed: {str(e)}") from e

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        Async call method (REQUIRED by NeMo Guardrails - not optional).

        NeMo Guardrails validates that custom providers have _acall implemented.
        This method is critical for the provider registration to succeed.

        Args:
            prompt: The prompt string to generate from
            stop: Optional stop sequences
            run_manager: Optional async callback manager
            **kwargs: Additional generation parameters

        Returns:
            Generated text response

        Raises:
            RuntimeError: If DSPy LM is not configured
            Exception: For other generation errors
        """
        try:
            lm = self._get_dspy_lm()
            logger.debug(f"DSPyNeMoLLM._acall: prompt length={len(prompt)}")

            response = await asyncio.to_thread(lm, prompt)
            result = self._extract_text_from_response(response)

            logger.debug(f"DSPyNeMoLLM._acall: result length={len(result)}")
            return result

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Error in DSPyNeMoLLM._acall: {str(e)}")
            raise RuntimeError(f"Async LLM generation failed: {str(e)}") from e

    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        Stream response synchronously (required for NeMo Guardrails streaming).

        CRITICAL: Must yield strings, not Generation objects.
        NeMo Guardrails expects raw string tokens for buffering and validation.

        Args:
            prompt: The prompt string to generate from
            stop: Optional stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Yields:
            String tokens (word-level chunks)

        Raises:
            RuntimeError: If streaming fails
        """
        try:
            lm = self._get_dspy_lm()
            logger.debug(f"DSPyNeMoLLM._stream: prompt length={len(prompt)}")

            response = lm(prompt)
            result = self._extract_text_from_response(response)

            if not result:
                logger.warning("Empty response from LLM in streaming mode")
                return

            # Split into word-level chunks for streaming
            words = result.split()
            logger.debug(f"DSPyNeMoLLM._stream: streaming {len(words)} word tokens")

            for i, word in enumerate(words):
                # Add space after each word except the last one
                token = word if i == len(words) - 1 else word + " "

                # Notify callback manager if present
                if run_manager:
                    run_manager.on_llm_new_token(token)

                yield token

        except Exception as e:
            logger.error(f"Error in DSPyNeMoLLM._stream: {str(e)}")
            raise RuntimeError(f"Streaming failed: {str(e)}") from e

    async def _astream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream response asynchronously (required for NeMo Guardrails async streaming).

        CRITICAL: Must yield strings, not Generation objects.
        NeMo Guardrails expects raw string tokens for buffering and validation.

        Args:
            prompt: The prompt string to generate from
            stop: Optional stop sequences
            run_manager: Optional async callback manager
            **kwargs: Additional generation parameters

        Yields:
            String tokens (word-level chunks)

        Raises:
            RuntimeError: If async streaming fails
        """
        try:
            lm = self._get_dspy_lm()
            logger.debug(f"DSPyNeMoLLM._astream: prompt length={len(prompt)}")

            # Generate full response in background thread to avoid blocking
            response = await asyncio.to_thread(lm, prompt)
            result = self._extract_text_from_response(response)

            if not result:
                logger.warning("Empty response from LLM in async streaming mode")
                return

            # Split into word-level chunks for streaming
            words = result.split()
            logger.debug(f"DSPyNeMoLLM._astream: streaming {len(words)} word tokens")

            for i, word in enumerate(words):
                # Add space after each word except the last one
                token = word if i == len(words) - 1 else word + " "

                # Notify callback manager if present
                if run_manager:
                    await run_manager.on_llm_new_token(token)

                yield token

                # Allow other async tasks to run
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Error in DSPyNeMoLLM._astream: {str(e)}")
            raise RuntimeError(f"Async streaming failed: {str(e)}") from e

    def _generate(
        self,
        prompts: List[str],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """
        Generate responses for multiple prompts.

        This method is used by NeMo for batch processing.

        Args:
            prompts: List of prompt strings
            stop: Optional stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation parameters

        Returns:
            LLMResult with generations for each prompt
        """
        logger.debug(f"DSPyNeMoLLM._generate called with {len(prompts)} prompts")

        generations: List[List[Generation]] = []

        for i, prompt in enumerate(prompts):
            try:
                text = self._call(prompt, stop=stop, run_manager=run_manager, **kwargs)
                generations.append([Generation(text=text)])
                logger.debug(f"Generated response {i + 1}/{len(prompts)}")
            except Exception as e:
                logger.error(f"Error generating response for prompt {i + 1}: {str(e)}")
                generations.append([Generation(text="")])

        return LLMResult(generations=generations, llm_output={})

    async def _agenerate(
        self,
        prompts: List[str],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """
        Async generate responses for multiple prompts.

        Args:
            prompts: List of prompt strings
            stop: Optional stop sequences
            run_manager: Optional async callback manager
            **kwargs: Additional generation parameters

        Returns:
            LLMResult with generations for each prompt
        """
        logger.debug(f"DSPyNeMoLLM._agenerate called with {len(prompts)} prompts")

        generations: List[List[Generation]] = []

        for i, prompt in enumerate(prompts):
            try:
                text = await self._acall(
                    prompt, stop=stop, run_manager=run_manager, **kwargs
                )
                generations.append([Generation(text=text)])
                logger.debug(f"Generated async response {i + 1}/{len(prompts)}")
            except Exception as e:
                logger.error(
                    f"Error generating async response for prompt {i + 1}: {str(e)}"
                )
                generations.append([Generation(text="")])

        return LLMResult(generations=generations, llm_output={})


class DSPyLLMProviderFactory:
    """
    Factory class for creating DSPyNeMoLLM instances.

    This class satisfies NeMo Guardrails' provider validation requirements
    by having the necessary methods on the factory itself, while still
    returning proper LLM instances when called.
    """

    def __call__(self, config: Optional[Dict[str, Any]] = None) -> DSPyNeMoLLM:
        """
        Create and return a DSPyNeMoLLM instance.

        Args:
            config: Optional configuration dictionary

        Returns:
            Configured DSPyNeMoLLM instance
        """
        if config is None:
            config = {}
        return DSPyNeMoLLM(**config)

    def _call(self, *args, **kwargs) -> str:
        """Placeholder - use the instance returned by __call__."""
        raise NotImplementedError(
            "This is a factory. Call the provider to get an LLM instance first."
        )

    async def _acall(self, *args, **kwargs) -> str:
        """Placeholder - use the instance returned by __call__."""
        raise NotImplementedError(
            "This is a factory. Call the provider to get an LLM instance first."
        )

    @property
    def _llm_type(self) -> str:
        """Return type identifier."""
        return "dspy-custom"
