"""RAG pipeline failure messages follow the detected language.

Covers the paths that cannot be triggered on purpose from the GUI: the output
guardrail blocking the bot's own answer, the token limit, and technical errors
(streaming and non-streaming). The LLM, retriever and guardrails are replaced by
fakes, so no real model is called.
"""

from typing import Any, AsyncIterator, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.request_models import OrchestrationRequest, OrchestrationResponse
from src.llm_orchestration_service import LLMOrchestrationService
from src.llm_orchestrator_config.llm_ochestrator_constants import (
    OUTPUT_GUARDRAIL_VIOLATION_MESSAGES,
    STREAM_TOKEN_LIMIT_MESSAGES,
    TECHNICAL_ISSUE_MESSAGES,
)
from src.llm_orchestrator_config.stream_config import StreamConfig
from src.orchestration.rag_pipeline import RagPipeline

LANGUAGES = ["et", "ru", "en"]


def _request(lang: str) -> OrchestrationRequest:
    request = OrchestrationRequest(
        chatId="chat-1",
        message="question",
        authorId="author-1",
        conversationHistory=[],
        url="opensearch-dashboard-test",
        environment="production",
    )
    # Normally stamped by the request preamble after language detection.
    setattr(request, "_detected_language", lang)  # noqa: B010
    return request


def _service() -> MagicMock:
    # spec= makes the fake follow the real service's interface: if a method the
    # pipeline calls is renamed or removed, these tests fail instead of passing.
    service = MagicMock(spec=LLMOrchestrationService)
    # Instance attributes are created in __init__, so spec does not know them.
    service.conversation_history_store = None
    service.langfuse_config = MagicMock(langfuse_client=None)
    # Return the plain content so assertions can compare message text directly.
    service.format_sse = lambda chat_id, content, buttons=None: content
    service._refine_user_prompt.return_value = (
        MagicMock(original_question="question", refined_questions=[]),
        {},
    )
    service._safe_retrieve_contextual_chunks = AsyncMock(
        return_value=[{"text": "some context"}]
    )
    service.store_streaming_inference = AsyncMock()
    return service


def _components(stream_with_guardrails: Any) -> Dict[str, Any]:  # noqa: ANN401
    response_generator = MagicMock()
    response_generator.check_scope_quick = AsyncMock(return_value=False)
    guardrails_adapter = MagicMock()
    guardrails_adapter.stream_with_guardrails = stream_with_guardrails
    return {
        "llm_manager": MagicMock(),
        "contextual_retriever": MagicMock(),
        "response_generator": response_generator,
        "guardrails_adapter": guardrails_adapter,
    }


async def _run_stream(lang: str, stream_with_guardrails: Any) -> List[str]:  # noqa: ANN401
    pipeline = RagPipeline(_service())
    with (
        patch(
            "src.orchestration.rag_pipeline.get_conversation_history",
            AsyncMock(return_value=([], None)),
        ),
        patch(
            "src.orchestration.rag_pipeline.get_lm_usage_since_split",
            return_value=({}, {}),
        ),
    ):
        return [
            chunk
            async for chunk in pipeline.stream(
                request=_request(lang),
                components=_components(stream_with_guardrails),
                stream_ctx=MagicMock(stream_id="stream-1", token_count=0),
                costs_metric={},
                time_metric={},
            )
        ]


class TestRagStreamingFailureLanguage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGUAGES)
    async def test_output_guardrail_block(self, lang: str) -> None:
        async def blocked(**kwargs: Any) -> AsyncIterator[str]:  # noqa: ANN401
            yield "I cannot respond to that"

        chunks = await _run_stream(lang, blocked)

        assert chunks == [OUTPUT_GUARDRAIL_VIOLATION_MESSAGES[lang], "END"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGUAGES)
    async def test_token_limit(self, lang: str) -> None:
        # ~4 characters per token, so this single chunk exceeds the limit.
        long_chunk = "a" * (StreamConfig.MAX_TOKENS_PER_STREAM * 4 + 8)

        async def too_long(**kwargs: Any) -> AsyncIterator[str]:  # noqa: ANN401
            yield long_chunk

        chunks = await _run_stream(lang, too_long)

        assert chunks[-2:] == [STREAM_TOKEN_LIMIT_MESSAGES[lang], "END"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lang", LANGUAGES)
    async def test_technical_issue_while_streaming(self, lang: str) -> None:
        async def crashing(**kwargs: Any) -> AsyncIterator[str]:  # noqa: ANN401
            raise RuntimeError("guardrails crashed")
            yield ""  # pragma: no cover - makes this an async generator

        chunks = await _run_stream(lang, crashing)

        assert chunks == [TECHNICAL_ISSUE_MESSAGES[lang], "END"]


class TestRagNonStreamingFailureLanguage:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_technical_issue_without_response_generator(self, lang: str) -> None:
        pipeline = RagPipeline(_service())

        response = pipeline.generate_response(
            llm_manager=MagicMock(),
            request=_request(lang),
            refined_output=MagicMock(),
            relevant_chunks=[],
            response_generator=None,
        )

        assert isinstance(response, OrchestrationResponse)
        assert response.content == TECHNICAL_ISSUE_MESSAGES[lang]
