"""API response formatter using DSPy — converts raw JSON API responses to natural language."""

import json
from typing import Any, AsyncIterator, Dict, List, Union

import dspy
import dspy.streaming
from dspy.streaming import StreamListener
from loguru import logger

from llm_orchestrator_config.llm_ochestrator_constants import get_localized_message

_MAX_ITEMS: int = 500
_MAX_RESPONSE_BYTES: int = 50_000


class APIResponseFormatterSignature(dspy.Signature):
    """Convert a raw API JSON response into a natural-language answer for the user.

    CRITICAL LANGUAGE RULE:
    - ALWAYS write the formatted_answer in the language specified by response_language.
    - IGNORE the language of any text inside api_response — the data may contain names or
      labels in a different language; the answer must still be in response_language.
    - IGNORE the language of user_query for output language decisions — short follow-up
      messages are unreliable indicators. Always use response_language.

    Rules:
    - Format data in a readable way using bullet points, numbered lists, or natural prose.
      Do NOT return raw JSON or wrap content in code blocks.
    - If api_response is empty, null, or marked as [EMPTY RESPONSE], respond with a polite
      message that no results were found for the query.
    - If api_response contains an error field or error status, explain the issue to the user
      in a friendly, non-technical way.
    - If the data contains more than 20 items, summarize the key highlights rather than
      listing every item. Always mention the total count when summarizing.
    - Output must be clean text — no markdown headers (##), no code blocks (```), no raw
      JSON. The answer must be ready for direct display to the user.
    - Be concise but complete. Prioritize the most relevant information for the user's query.

    STRICT ENDING RULE — HIGHEST PRIORITY:
    The formatted_answer MUST end immediately after the last data point. It is FORBIDDEN to
    append any sentence that:
    - offers to provide more details (e.g. "If you need statistics for a specific member...")
    - invites the user to ask a follow-up question (e.g. "Let me know if...", "Feel free to ask...")
    - mentions that a dataset is large or partial (e.g. "only a sample is shown here")
    - suggests the user can specify a name, party, or other filter
    The very last character of formatted_answer must be part of the actual data, not a helper offer.
    """

    user_query: str = dspy.InputField(
        desc="The user's original question or request, in Estonian, Russian, or English"
    )
    api_response: str = dspy.InputField(
        desc=(
            "The raw JSON response from the API, as a string. "
            "May be empty, null, an error, or a large dataset."
        )
    )
    endpoint_description: str = dspy.InputField(
        desc=(
            "A short description of what the API endpoint does "
            "(e.g., 'Get public holidays for a country')"
        )
    )
    response_language: str = dspy.InputField(
        desc=(
            "The language to write the answer in, detected from the user's first message: "
            "'English', 'Estonian', or 'Russian'. "
            "Always use this — do not infer language from api_response content."
        )
    )

    formatted_answer: str = dspy.OutputField(
        desc=(
            "A clean, natural-language answer derived from the api_response, "
            "written entirely in the language specified by response_language. "
            "No raw JSON, no code blocks, no markdown headers. "
            "MUST end after the last data point. "
            "FORBIDDEN: any closing sentence offering more help, inviting follow-up questions, "
            "mentioning that the dataset is partial, or suggesting the user specify a name/party."
        )
    )


_LANGUAGE_NAMES: Dict[str, str] = {"en": "English", "et": "Estonian", "ru": "Russian"}

_FORMATTER_ERROR_MESSAGES: Dict[str, str] = {
    "et": "Vastuse kuvamine ebaõnnestus. Palun proovige uuesti.",
    "ru": "Не удалось отобразить ответ. Пожалуйста, попробуйте ещё раз.",
    "en": "I was unable to format the response. Please try again.",
}
"""Localized fallback shown when APIResponseFormatterModule.forward() raises an exception."""


class APIResponseFormatterModule(dspy.Module):
    """DSPy Module that converts raw API JSON responses into natural-language answers."""

    def __init__(self) -> None:
        """Initialize formatter with a direct DSPy Predict."""
        super().__init__()
        self.formatter = dspy.Predict(APIResponseFormatterSignature)

    def forward(
        self,
        user_query: str,
        api_response: Union[str, Dict[str, Any], List[Any]],
        endpoint_description: str,
        detected_language: str = "en",
    ) -> str:
        """Convert a raw API response to a natural-language answer.

        Args:
            user_query: The user's original question.
            api_response: The raw API response — a JSON string, dict, or list.
            endpoint_description: A short description of what the endpoint does.
            detected_language: ISO language code from the agentic loop session
                ('en', 'et', 'ru'). Defaults to 'en'. This is the authoritative
                language for the answer — the LLM will not infer it from the data.

        Returns:
            A clean, natural-language answer ready for display to the user.
        """
        try:
            normalized = self._normalize_response(api_response)
            normalized = self._annotate_empty(normalized)
            normalized = self._truncate_if_needed(normalized)
            response_language = _LANGUAGE_NAMES.get(detected_language, "English")

            result = self.formatter(
                user_query=user_query,
                api_response=normalized,
                endpoint_description=endpoint_description,
                response_language=response_language,
            )
            return result.formatted_answer  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(
                f"APIResponseFormatterModule.forward failed: {e}", exc_info=True
            )
            safe_language = (
                detected_language
                if detected_language in _FORMATTER_ERROR_MESSAGES
                else "en"
            )
            return get_localized_message(_FORMATTER_ERROR_MESSAGES, safe_language)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_stream_predictor(self) -> Any:
        """Return a fresh streamified predictor for each call.

        A new wrapper is created on every invocation because ``dspy.configure(lm=...)``
        is called per request (each ``LLMManager`` instantiation reconfigures the global
        DSPy LM).  A cached wrapper retains a stale reference to the old LM patch and
        produces a bare ``dspy.Prediction`` instead of ``StreamResponse`` tokens on
        subsequent calls.  Re-creating the wrapper is cheap (no LLM I/O).
        """
        logger.debug(
            "APIResponseFormatterModule: creating fresh streamify wrapper "
            "for formatted_answer field"
        )
        listener = StreamListener(signature_field_name="formatted_answer")
        return dspy.streamify(self.formatter, stream_listeners=[listener])

    async def stream_forward(
        self,
        user_query: str,
        api_response: Union[str, Dict[str, Any], List[Any]],
        endpoint_description: str,
        detected_language: str = "en",
    ) -> AsyncIterator[str]:
        """Stream formatted_answer tokens using DSPy native streaming.
        Yields individual token strings as they arrive from the LLM.

        Fallback chain:
        1. DSPy ``StreamResponse`` tokens (true token-by-token streaming)
        2. Final ``dspy.Prediction.formatted_answer`` (if streamify yields no tokens)
        3. Blocking ``forward()`` call (if no Prediction was received)
        4. Localized error message on any exception.

        Args:
            user_query: The user's original question.
            api_response: Raw API response (dict, list, or string).
            endpoint_description: Short description of what the endpoint does.
            detected_language: ISO code ('en', 'et', 'ru'). Defaults to 'en'.

        Yields:
            Token strings from the LLM ``formatted_answer`` field.
        """
        safe_language = (
            detected_language
            if detected_language in _FORMATTER_ERROR_MESSAGES
            else "en"
        )
        try:
            normalized = self._normalize_response(api_response)
            normalized = self._annotate_empty(normalized)
            normalized = self._truncate_if_needed(normalized)
            response_language = _LANGUAGE_NAMES.get(detected_language, "English")

            stream_predictor = self._get_stream_predictor()
            output_stream = stream_predictor(
                user_query=user_query,
                api_response=normalized,
                endpoint_description=endpoint_description,
                response_language=response_language,
            )

            stream_started = False
            token_count = 0
            async for chunk in output_stream:
                if isinstance(chunk, dspy.streaming.StreamResponse):
                    if chunk.signature_field_name == "formatted_answer":
                        stream_started = True
                        token_count += 1
                        yield chunk.chunk
                elif isinstance(chunk, dspy.Prediction):
                    # dspy.streamify did not stream individual tokens — yield the
                    # full answer from the final Prediction as a single frame.
                    if not stream_started:
                        answer = getattr(chunk, "formatted_answer", None)
                        if answer:
                            logger.info(
                                "APIResponseFormatterModule.stream_forward: "
                                "no StreamResponse tokens — yielding full Prediction answer"
                            )
                            stream_started = True
                            yield answer

            if stream_started and token_count > 0:
                logger.debug(
                    f"APIResponseFormatterModule.stream_forward: streamed {token_count} tokens"
                )

            if not stream_started:
                # Last-resort fallback: blocking forward() — covers cases where
                # dspy.streamify yields neither StreamResponse nor Prediction.
                logger.warning(
                    "APIResponseFormatterModule.stream_forward: "
                    "streamify produced no tokens and no Prediction — using blocking forward()"
                )
                result = self.forward(
                    user_query=user_query,
                    api_response=api_response,
                    endpoint_description=endpoint_description,
                    detected_language=detected_language,
                )
                yield result

        except Exception as e:
            logger.error(
                f"APIResponseFormatterModule.stream_forward failed: {e}", exc_info=True
            )
            yield get_localized_message(_FORMATTER_ERROR_MESSAGES, safe_language)

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_response(
        api_response: Union[str, Dict[str, Any], List[Any]],
    ) -> str:
        """Convert dict or list inputs to a JSON string."""
        if isinstance(api_response, (dict, list)):
            return json.dumps(api_response, ensure_ascii=False)
        return str(api_response)

    @staticmethod
    def _annotate_empty(api_response_str: str) -> str:
        """Annotate obviously empty responses so the LLM handles them gracefully."""
        try:
            parsed = json.loads(api_response_str)
        except (json.JSONDecodeError, ValueError):
            return api_response_str

        if parsed is None or parsed == [] or parsed == {}:
            return "[EMPTY RESPONSE: The API returned no data for this query]"
        return api_response_str

    @staticmethod
    def _truncate_if_needed(api_response_str: str) -> str:
        """Truncate responses that exceed the item count or byte-size limits."""
        try:
            parsed = json.loads(api_response_str)
        except (json.JSONDecodeError, ValueError):
            parsed = None

        if isinstance(parsed, list) and len(parsed) > _MAX_ITEMS:
            total = len(parsed)
            truncated = json.dumps(parsed[:_MAX_ITEMS], ensure_ascii=False)
            api_response_str = (
                f"[NOTE: Response truncated to {_MAX_ITEMS} of {total} total items]\n"
                + truncated
            )

        encoded = api_response_str.encode("utf-8")
        if len(encoded) > _MAX_RESPONSE_BYTES:
            truncated_str = encoded[:_MAX_RESPONSE_BYTES].decode(
                "utf-8", errors="ignore"
            )
            return truncated_str + "\n[NOTE: Response truncated due to size limit]"

        return api_response_str
