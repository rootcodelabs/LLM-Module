"""API response formatter using DSPy — converts raw JSON API responses to natural language."""

import json
from typing import Any, Dict, List, Union

import dspy
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
            "No raw JSON, no code blocks, no markdown headers."
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
