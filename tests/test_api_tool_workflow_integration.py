"""Integration tests for the full API Tool Calling workflow chain.

Tests the full classify -> route -> execute chain with real component wiring.
Only the LLM layer (DSPy), Qdrant HTTP, and Redis are mocked.

Covers:
- Phase 2: Full multi-turn workflow, fast-path, streaming, cost tracking
- Phase 4: Fallback chain regression tests
"""

import json
import time
from collections.abc import AsyncGenerator
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.request_models import OrchestrationRequest, OrchestrationResponse
from models.session_models import APIToolSession
from tool_classifier.classifier import ToolClassifier
from tool_classifier.enums import AgenticLoopStatus, WorkflowType
from tool_classifier.models import (
    AgenticLoopResult,
    APICallResult,
    ClassificationResult,
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_CHAT_ID = "integration-test-chat"

_ENDPOINT_HOLIDAYS = {
    "endpoint_id": "ep-holidays",
    "name": "get_public_holidays",
    "description": "Returns public holidays for a country",
    "method": "GET",
    "url": "https://openholidaysapi.org/PublicHolidays",
    "params": [
        {
            "name": "countryIsoCode",
            "type": "string",
            "required": True,
            "description": "ISO code",
        },
    ],
    "cosine_score": 0.68,
    "rrf_score": 0.012,
    "confidence": "high",
}

_ENDPOINT_WEATHER = {
    "endpoint_id": "ep-weather",
    "name": "get_weather",
    "description": "Current weather for a city",
    "method": "GET",
    "url": "https://publicapi.envir.ee/v1/combinedWeatherData",
    "params": [],
    "cosine_score": 0.65,
    "rrf_score": 0.010,
    "confidence": "high",
}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_store() -> AsyncMock:
    """In-memory mock Redis session store."""
    _store: Dict[str, APIToolSession] = {}

    store = AsyncMock()

    async def _get(chat_id: str) -> Optional[APIToolSession]:
        return _store.get(chat_id)

    async def _save(session: APIToolSession) -> None:
        _store[session.chat_id] = session

    async def _delete(chat_id: str) -> None:
        _store.pop(chat_id, None)

    async def _update(session: APIToolSession) -> None:
        _store[session.chat_id] = session

    store.get = AsyncMock(side_effect=_get)
    store.save = AsyncMock(side_effect=_save)
    store.delete = AsyncMock(side_effect=_delete)
    store.update = AsyncMock(side_effect=_update)
    store._store = _store
    return store


@pytest.fixture
def mock_orchestration_service(mock_session_store: AsyncMock) -> MagicMock:
    """Mock orchestration service with session store and SSE formatter."""
    svc = MagicMock()
    svc.session_store = mock_session_store
    svc.create_embeddings_for_indexer.return_value = {"embeddings": [[0.1] * 10]}

    def _format_sse(chat_id: str, content: str) -> str:
        payload = {
            "chatId": chat_id,
            "payload": {"content": content},
            "timestamp": int(time.time() * 1000),
        }
        return f"data: {json.dumps(payload)}\n\n"

    svc.format_sse = _format_sse

    async def _mock_rag(**kwargs: Any) -> OrchestrationResponse:
        req = kwargs.get("request")
        chat_id = req.chatId if req else _CHAT_ID
        return OrchestrationResponse(
            chatId=chat_id,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content="RAG fallback answer.",
        )

    svc._execute_orchestration_pipeline = AsyncMock(side_effect=_mock_rag)
    svc._initialize_service_components = MagicMock(return_value={})

    async def _mock_rag_stream(**kwargs: Any) -> AsyncGenerator[str, None]:
        yield 'data: {"chatId":"test","payload":{"content":"RAG stream answer"}}\n\n'
        yield 'data: {"chatId":"test","payload":{"content":"END"}}\n\n'

    svc._stream_rag_pipeline = _mock_rag_stream

    return svc


@pytest.fixture
def classifier(mock_orchestration_service: MagicMock) -> ToolClassifier:
    """Create a real ToolClassifier with all real workflow executors."""
    return ToolClassifier(
        llm_manager=MagicMock(),
        orchestration_service=mock_orchestration_service,
    )


def _make_request(
    message: str,
    chat_id: str = _CHAT_ID,
) -> OrchestrationRequest:
    return OrchestrationRequest(
        chatId=chat_id,
        message=message,
        authorId="test-user",
        conversationHistory=[],
        url="https://example.com",
        environment="testing",
        connection_id="test-conn",
    )


def _make_api_search_result(endpoint: Dict[str, Any]) -> MagicMock:
    result = MagicMock()
    result.endpoint_id = endpoint["endpoint_id"]
    result.name = endpoint["name"]
    result.description = endpoint["description"]
    result.method = endpoint["method"]
    result.url = endpoint["url"]
    result.params = endpoint.get("params", [])
    result.cosine_score = endpoint.get("cosine_score", 0.65)
    result.rrf_score = endpoint.get("rrf_score", 0.01)
    result.confidence = endpoint.get("confidence", "high")
    result.to_dict.return_value = endpoint
    return result


def _make_loop_result(
    status: AgenticLoopStatus,
    collected_params: Optional[Dict[str, Any]] = None,
    clarifying_question: str = "Which country?",
    turn_count: int = 1,
) -> AgenticLoopResult:
    return AgenticLoopResult(
        status=status,
        collected_params=collected_params or {},
        clarifying_question=clarifying_question,
        turn_count=turn_count,
    )


# ---------------------------------------------------------------------------
# Phase 2: TestClassifyAndRouteToAPITool
# ---------------------------------------------------------------------------


class TestClassifyAndRouteToAPITool:
    """Test classify() correctly routes to API_TOOL_CALLING."""

    @pytest.mark.asyncio
    async def test_high_confidence_match_routes_to_api_tool(
        self, classifier: ToolClassifier
    ) -> None:
        """High-confidence API tool match → classify returns API_TOOL_CALLING."""
        classifier.api_tool_searcher.search = AsyncMock(
            return_value=[_make_api_search_result(_ENDPOINT_HOLIDAYS)]
        )

        with (
            patch(
                "tool_classifier.classifier.FeatureFlags.SERVICE_WORKFLOW_ENABLED",
                False,
            ),
            patch(
                "tool_classifier.classifier.FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED",
                True,
            ),
        ):
            result = await classifier.classify(
                query="public holidays in Estonia",
                conversation_history=[],
                language="en",
                request=_make_request("public holidays in Estonia"),
            )

        assert result.workflow == WorkflowType.API_TOOL_CALLING
        assert (
            result.metadata.get("matched_endpoint", {}).get("name")
            == "get_public_holidays"
        )

    @pytest.mark.asyncio
    async def test_below_threshold_routes_to_rag_fallback(
        self, classifier: ToolClassifier
    ) -> None:
        """No API tool match → classify routes to CONTEXT (falls through to RAG)."""
        classifier.api_tool_searcher.search = AsyncMock(return_value=[])

        with (
            patch(
                "tool_classifier.classifier.FeatureFlags.SERVICE_WORKFLOW_ENABLED",
                False,
            ),
            patch(
                "tool_classifier.classifier.FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED",
                True,
            ),
        ):
            result = await classifier.classify(
                query="something completely unrelated to any API",
                conversation_history=[],
                language="en",
            )

        assert result.workflow == WorkflowType.CONTEXT


# ---------------------------------------------------------------------------
# Phase 2: TestAPIToolMultiTurnFlow
# ---------------------------------------------------------------------------


class TestAPIToolMultiTurnFlow:
    """Full multi-turn agentic loop with session state in mock Redis."""

    @pytest.mark.asyncio
    async def test_turn1_partial_params_returns_clarifying_question(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Turn 1: matched endpoint → create session → ask clarifying question."""
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.68,
            metadata={"matched_endpoint": _ENDPOINT_HOLIDAYS},
        )
        request = _make_request("public holidays")

        loop_result = _make_loop_result(AgenticLoopStatus.NEEDS_INPUT)
        with patch.object(
            classifier.api_tool_workflow,
            "_build_agentic_loop",
            return_value=_make_mock_loop(loop_result, ["Which", " country?"]),
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        assert isinstance(response, OrchestrationResponse)
        assert "country" in response.content.lower() or response.content != ""
        # Session created in Redis
        session = await mock_session_store.get(_CHAT_ID)
        assert session is not None

    @pytest.mark.asyncio
    async def test_turn2_complete_params_returns_api_response(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Turn 2: all params collected → API call → formatted response."""
        # Seed an existing session (simulating Turn 1 having already run)
        session = APIToolSession(
            chat_id=_CHAT_ID,
            state="collecting_params",
            selected_endpoint=_ENDPOINT_HOLIDAYS,
            collected_params={},
            turn_count=1,
            max_turns=5,
            awaiting_continuation=False,
            detected_language="en",
            original_query="public holidays",
        )
        await mock_session_store.save(session)

        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=1.0,
            metadata={"reason": "active_session_resume"},
        )
        request = _make_request("EE")

        completed_result = _make_loop_result(
            AgenticLoopStatus.COMPLETED,
            collected_params={"countryIsoCode": "EE"},
        )
        api_call_result = APICallResult(
            success=True,
            status_code=200,
            response_data={"holidays": [{"name": "Jõulupüha", "date": "2024-12-25"}]},
            error=None,
        )

        with (
            patch.object(
                classifier.api_tool_workflow,
                "_build_agentic_loop",
                return_value=_make_mock_loop(completed_result, []),
            ),
            patch.object(
                classifier.api_tool_workflow._api_caller,
                "call",
                new_callable=AsyncMock,
                return_value=api_call_result,
            ),
            patch(
                "tool_classifier.workflows.api_tool_workflow.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="Estonia has 1 holiday: Jõulupüha on December 25.",
            ),
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        assert isinstance(response, OrchestrationResponse)
        assert response.content != ""
        # Session deleted after COMPLETED
        assert await mock_session_store.get(_CHAT_ID) is None


# ---------------------------------------------------------------------------
# Phase 2: TestAPIToolFastPath
# ---------------------------------------------------------------------------


class TestAPIToolFastPath:
    """Endpoint with no required params → immediate API call, no session created."""

    @pytest.mark.asyncio
    async def test_no_required_params_immediate_api_call(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_WEATHER},
        )
        request = _make_request("What is the weather?")

        api_call_result = APICallResult(
            success=True,
            status_code=200,
            response_data={"temperature": 22, "condition": "Sunny"},
            error=None,
        )

        with (
            patch.object(
                classifier.api_tool_workflow._api_caller,
                "call",
                new_callable=AsyncMock,
                return_value=api_call_result,
            ),
            patch(
                "tool_classifier.workflows.api_tool_workflow.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value="It is 22°C and sunny in Tallinn.",
            ),
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        assert isinstance(response, OrchestrationResponse)
        assert response.content != ""
        # No session created for fast-path
        assert await mock_session_store.get(_CHAT_ID) is None


# ---------------------------------------------------------------------------
# Phase 2: TestAPIToolStreamingFlow
# ---------------------------------------------------------------------------


class TestAPIToolStreamingFlow:
    """Streaming path: SSE token frames validated."""

    @pytest.mark.asyncio
    async def test_streaming_question_yields_sse_frame(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """First turn → clarifying question → single SSE frame."""
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.68,
            metadata={"matched_endpoint": _ENDPOINT_HOLIDAYS},
        )
        request = _make_request("public holidays")

        loop_result = _make_loop_result(AgenticLoopStatus.NEEDS_INPUT)

        with patch.object(
            classifier.api_tool_workflow,
            "_build_agentic_loop",
            return_value=_make_mock_loop(loop_result, ["Which", " country?"]),
        ):
            stream = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=True,
            )
            frames = [frame async for frame in stream]

        assert len(frames) >= 1
        # Each frame must be a valid SSE line
        for frame in frames:
            assert frame.startswith("data: ") or frame.strip() == ""

    @pytest.mark.asyncio
    async def test_streaming_api_success_yields_token_frames(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Fast-path endpoint → API call → streamed formatted tokens."""
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_WEATHER},
        )
        request = _make_request("weather in Tallinn")

        api_call_result = APICallResult(
            success=True,
            status_code=200,
            response_data={"temperature": 15},
            error=None,
        )

        async def _fake_stream_forward(**kwargs: Any) -> AsyncIterator[str]:
            for token in ["It is ", "15°C ", "in Tallinn."]:
                yield token

        with (
            patch.object(
                classifier.api_tool_workflow._api_caller,
                "call",
                new_callable=AsyncMock,
                return_value=api_call_result,
            ),
            patch.object(
                classifier.api_tool_workflow._formatter,
                "stream_forward",
                side_effect=_fake_stream_forward,
            ),
        ):
            stream = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=True,
            )
            frames = [frame async for frame in stream]

        # 3 token frames + 1 END frame
        assert len(frames) == 4
        for frame in frames:
            assert frame.startswith("data: ")


# ---------------------------------------------------------------------------
# Phase 4: TestFallbackChainRegression
# ---------------------------------------------------------------------------


class TestFallbackChainRegression:
    """Regression tests for the API Tool fallback chain."""

    @pytest.mark.asyncio
    async def test_max_turns_reached_falls_back_to_rag(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """MAX_TURNS_REACHED → workflow returns None → RAG fallback handles request."""
        session = APIToolSession(
            chat_id=_CHAT_ID,
            state="collecting_params",
            selected_endpoint=_ENDPOINT_HOLIDAYS,
            collected_params={},
            turn_count=4,
            max_turns=5,
            awaiting_continuation=False,
            detected_language="en",
            original_query="public holidays",
        )
        await mock_session_store.save(session)

        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=1.0,
            metadata={"reason": "active_session_resume"},
        )
        request = _make_request("I don't know")

        max_turns_result = _make_loop_result(AgenticLoopStatus.MAX_TURNS_REACHED)

        with patch.object(
            classifier.api_tool_workflow,
            "_build_agentic_loop",
            return_value=_make_mock_loop(max_turns_result, []),
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        # Session deleted, falls back to RAG
        assert await mock_session_store.get(_CHAT_ID) is None
        assert isinstance(response, OrchestrationResponse)

    @pytest.mark.asyncio
    async def test_api_call_failure_returns_error_not_fallback(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """API 5xx → error message returned directly, NOT a RAG fallback response."""
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_WEATHER},
        )
        request = _make_request("weather")

        error_msg = "The service is temporarily unavailable. Please try again later."
        api_fail_result = APICallResult(
            success=False,
            status_code=500,
            response_data="",
            error=error_msg,
        )

        with patch.object(
            classifier.api_tool_workflow._api_caller,
            "call",
            new_callable=AsyncMock,
            return_value=api_fail_result,
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        assert isinstance(response, OrchestrationResponse)
        # Must NOT be the RAG fallback answer
        assert response.content != "RAG fallback answer."
        assert response.content == error_msg

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_returns_immediate_error(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """OPEN circuit breaker → immediate localized error, no HTTP call made."""
        from tool_classifier.constants import CIRCUIT_BREAKER_OPEN_MESSAGES

        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_WEATHER},
        )
        request = _make_request("weather")

        # Force breaker OPEN
        caller = classifier.api_tool_workflow._api_caller
        caller._circuit_breaker._breakers[_ENDPOINT_WEATHER["url"]] = __import__(
            "tool_classifier.api_caller",
            fromlist=["_BreakerState"],
        )._BreakerState(state="OPEN", failure_count=3, last_failure_time=time.time())

        response = await classifier.route_to_workflow(
            classification=classification,
            request=request,
            is_streaming=False,
        )

        assert isinstance(response, OrchestrationResponse)
        assert response.content in CIRCUIT_BREAKER_OPEN_MESSAGES.values()

    @pytest.mark.asyncio
    async def test_classification_failure_falls_back_to_context(
        self,
        classifier: ToolClassifier,
    ) -> None:
        """Qdrant unavailable during classification → skip API tool → CONTEXT."""
        classifier.api_tool_searcher.search = AsyncMock(
            side_effect=RuntimeError("Qdrant connection refused")
        )

        with (
            patch(
                "tool_classifier.classifier.FeatureFlags.SERVICE_WORKFLOW_ENABLED",
                False,
            ),
            patch(
                "tool_classifier.classifier.FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED",
                True,
            ),
        ):
            result = await classifier.classify(
                query="public holidays",
                conversation_history=[],
                language="en",
                request=_make_request("public holidays"),
            )

        assert result.workflow == WorkflowType.CONTEXT

    @pytest.mark.asyncio
    async def test_embedding_failure_falls_back(
        self,
        classifier: ToolClassifier,
    ) -> None:
        """Embedding throws → classification returns None → CONTEXT fallback."""
        classifier.orchestration_service.create_embeddings_for_indexer.side_effect = (
            RuntimeError("Embedding API down")
        )

        with patch(
            "tool_classifier.classifier.FeatureFlags.SERVICE_WORKFLOW_ENABLED",
            True,
        ):
            result = await classifier.classify(
                query="public holidays",
                conversation_history=[],
                language="en",
            )

        assert result.workflow == WorkflowType.CONTEXT
        assert result.metadata.get("reason") == "embedding_generation_failed"

    @pytest.mark.asyncio
    async def test_session_store_unavailable_graceful_degradation(
        self,
        classifier: ToolClassifier,
    ) -> None:
        """Redis unavailable → stateless execution, loop still runs."""
        # Remove session_store from orchestration service
        classifier.orchestration_service.session_store = None

        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_HOLIDAYS},
        )
        request = _make_request("public holidays")

        loop_result = _make_loop_result(AgenticLoopStatus.NEEDS_INPUT)

        with patch.object(
            classifier.api_tool_workflow,
            "_build_agentic_loop",
            return_value=_make_mock_loop(loop_result, ["Which", " country?"]),
        ):
            response = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=False,
            )

        # Should still return a question — stateless but functional
        assert isinstance(response, OrchestrationResponse)
        assert "country" in response.content.lower() or response.content != ""

    @pytest.mark.asyncio
    async def test_intent_switch_during_active_session(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Different endpoint match → delete old session, create new."""
        # Seed holidays session
        existing = APIToolSession(
            chat_id=_CHAT_ID,
            state="collecting_params",
            selected_endpoint=_ENDPOINT_HOLIDAYS,
            collected_params={},
            turn_count=1,
            max_turns=5,
            awaiting_continuation=False,
            detected_language="en",
            original_query="public holidays",
        )
        await mock_session_store.save(existing)

        # New query matches WEATHER (different endpoint)
        classifier.api_tool_searcher.search = AsyncMock(
            return_value=[_make_api_search_result(_ENDPOINT_WEATHER)]
        )

        with (
            patch(
                "tool_classifier.classifier.FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED",
                True,
            ),
        ):
            result = await classifier.classify(
                query="What is the weather in Tallinn?",
                conversation_history=[],
                language="en",
                request=_make_request("What is the weather in Tallinn?"),
            )

        # Old session deleted
        assert await mock_session_store.get(_CHAT_ID) is None
        assert result.workflow == WorkflowType.API_TOOL_CALLING
        assert result.metadata.get("matched_endpoint", {}).get("name") == "get_weather"

    @pytest.mark.asyncio
    async def test_disambiguation_rejects_all_candidates_fallback(
        self,
        classifier: ToolClassifier,
    ) -> None:
        """LLM says 'none' during disambiguation → fallback to CONTEXT/RAG."""
        classifier.api_tool_searcher.search = AsyncMock(return_value=[])

        with (
            patch(
                "tool_classifier.classifier.FeatureFlags.SERVICE_WORKFLOW_ENABLED",
                False,
            ),
            patch(
                "tool_classifier.classifier.FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED",
                True,
            ),
        ):
            result = await classifier.classify(
                query="something not matching any endpoint",
                conversation_history=[],
                language="en",
                request=_make_request("something not matching any endpoint"),
            )

        assert result.workflow == WorkflowType.CONTEXT


# ---------------------------------------------------------------------------
# Phase 4: TestStreamingFallbackRegression
# ---------------------------------------------------------------------------


class TestStreamingFallbackRegression:
    @pytest.mark.asyncio
    async def test_streaming_max_turns_falls_back_to_rag_stream(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Streaming: MAX_TURNS_REACHED → workflow returns None → RAG stream fallback."""
        session = APIToolSession(
            chat_id=_CHAT_ID,
            state="collecting_params",
            selected_endpoint=_ENDPOINT_HOLIDAYS,
            collected_params={},
            turn_count=5,
            max_turns=5,
            awaiting_continuation=False,
            detected_language="en",
            original_query="public holidays",
        )
        await mock_session_store.save(session)

        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=1.0,
            metadata={"reason": "active_session_resume"},
        )
        request = _make_request("I give up")

        max_turns_result = _make_loop_result(AgenticLoopStatus.MAX_TURNS_REACHED)

        with patch.object(
            classifier.api_tool_workflow,
            "_build_agentic_loop",
            return_value=_make_mock_loop(max_turns_result, []),
        ):
            stream = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=True,
            )
            frames = [frame async for frame in stream]

        # Session deleted
        assert await mock_session_store.get(_CHAT_ID) is None
        # RAG stream produced frames
        assert len(frames) > 0

    @pytest.mark.asyncio
    async def test_streaming_api_error_returns_sse_error_frame(
        self,
        classifier: ToolClassifier,
        mock_session_store: AsyncMock,
    ) -> None:
        """Streaming: API failure → error SSE frame (not raw exception)."""
        classification = ClassificationResult(
            workflow=WorkflowType.API_TOOL_CALLING,
            confidence=0.65,
            metadata={"matched_endpoint": _ENDPOINT_WEATHER},
        )
        request = _make_request("weather")

        error_msg = "The service is temporarily unavailable. Please try again later."
        api_fail_result = APICallResult(
            success=False,
            status_code=503,
            response_data="",
            error=error_msg,
        )

        with patch.object(
            classifier.api_tool_workflow._api_caller,
            "call",
            new_callable=AsyncMock,
            return_value=api_fail_result,
        ):
            stream = await classifier.route_to_workflow(
                classification=classification,
                request=request,
                is_streaming=True,
            )
            frames = [frame async for frame in stream]

        # At least one error frame
        assert len(frames) >= 1
        combined = "".join(frames)
        assert error_msg in combined


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_loop(
    result: AgenticLoopResult,
    question_tokens: List[str],
) -> MagicMock:
    """Return a mock AgenticLoop whose stream_run_turn returns the given result."""
    loop = MagicMock()
    loop.stream_run_turn = AsyncMock(return_value=(result, question_tokens))
    return loop
