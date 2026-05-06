"""API Tool Calling Workflow Executor — Layer 2 of the classification chain."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from models.session_models import APIToolSession
from tool_classifier.agentic_loop import AgenticLoop
from tool_classifier.base_workflow import BaseWorkflow
from tool_classifier.enums import AgenticLoopStatus
from tool_classifier.param_extractor import ParamExtractionModule


class APIToolWorkflowExecutor(BaseWorkflow):
    """Executes API Tool Calling workflow (Layer 2).

    Handles queries that matched an API endpoint in api_tool_collection.

    On the first turn for a chat_id the matched endpoint is read from context
    (populated by ToolClassifier.classify()).  Subsequent turns resume from the
    persisted Redis session — context["matched_endpoint"] is ignored once a
    session exists.

    The executor manages the agentic loop lifecycle:
      - creates the session on turn 1
      - resumes it on turns 2-N
      - deletes it on COMPLETED or MAX_TURNS_REACHED

    When all required params are collected (COMPLETED) the response content is a
    JSON string with keys ``status``, ``endpoint``, and ``collected_params``.
    The API call and response formatting are handled by the next task.
    """

    def __init__(self, orchestration_service: Optional[Any] = None) -> None:
        self.orchestration_service = orchestration_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_session_store(self) -> Optional[Any]:
        """Return the session store from the orchestration service, or None."""
        if self.orchestration_service is None:
            return None
        return getattr(self.orchestration_service, "session_store", None)

    def _build_agentic_loop(self, session_store: Any) -> AgenticLoop:
        """Construct a fresh AgenticLoop for one request."""
        return AgenticLoop(
            session_store=session_store,
            param_extractor=ParamExtractionModule(),
        )

    @staticmethod
    def _required_params(params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [p for p in params if isinstance(p, dict) and p.get("required", False)]

    @staticmethod
    def _build_completed_response(
        chat_id: str,
        endpoint: Dict[str, Any],
        collected_params: Dict[str, Any],
    ) -> OrchestrationResponse:
        content = json.dumps(
            {
                "status": "params_collected",
                "endpoint": {
                    "name": endpoint.get("name"),
                },
                "collected_params": collected_params,
            },
            ensure_ascii=False,
        )
        return OrchestrationResponse(
            chatId=chat_id,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=content,
        )

    @staticmethod
    def _build_question_response(chat_id: str, question: str) -> OrchestrationResponse:
        return OrchestrationResponse(
            chatId=chat_id,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=question,
        )

    # ------------------------------------------------------------------
    # Core loop handler — shared by async and streaming paths
    # ------------------------------------------------------------------

    async def _run(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[OrchestrationResponse]:
        """Execute one turn of the agentic loop and return a response.

        Handles session creation (turn 1), resumption (turn 2-N), and all
        AgenticLoopStatus outcomes.  Returns None to signal a fallback only
        when there is genuinely nothing to work with (no endpoint in context
        and no active session).
        """
        chat_id = request.chatId
        session_store = self._get_session_store()

        # ── Try to resume an existing session ────────────────────────────
        session: Optional[APIToolSession] = None
        if session_store is not None:
            session = await session_store.get(chat_id)

        if session is not None:
            # Resume path — endpoint comes from persisted session
            endpoint = session.selected_endpoint
            if endpoint is None:
                # Corrupt session: delete and fall back
                logger.warning(
                    f"[{chat_id}] APIToolWorkflow: session has no endpoint — deleting"
                )
                if session_store is not None:
                    await session_store.delete(chat_id)
                return None

            logger.info(
                f"[{chat_id}] APIToolWorkflow: resuming session "
                f"(turn={session.turn_count}, endpoint={endpoint.get('name')!r})"
            )
        else:
            # New-session path — endpoint must come from classifier context
            endpoint = context.get("matched_endpoint")
            if not endpoint:
                logger.warning(
                    f"[{chat_id}] APIToolWorkflow: no matched_endpoint in context "
                    f"and no active session — falling back"
                )
                return None

            params_schema: List[Dict[str, Any]] = endpoint.get("params", [])

            # Fast path: no required params — nothing to collect, return immediately
            if not self._required_params(params_schema):
                logger.info(
                    f"[{chat_id}] APIToolWorkflow: endpoint {endpoint.get('name')!r} "
                    f"has no required params — fast path"
                )
                return self._build_completed_response(chat_id, endpoint, {})

            # Create a new session before running the first loop turn
            if session_store is not None:
                new_session = APIToolSession(
                    chat_id=chat_id,
                    state="collecting_params",
                    selected_endpoint=endpoint,
                    collected_params={},
                    turn_count=0,
                    max_turns=5,
                    awaiting_continuation=False,
                    detected_language=getattr(request, "_detected_language", "en"),
                )
                await session_store.save(new_session)
                session = new_session
            else:
                # Redis unavailable — create an in-memory placeholder so the
                # loop still runs (single-turn degradation: no persistence).
                logger.warning(
                    f"[{chat_id}] APIToolWorkflow: Redis unavailable — "
                    f"running loop without session persistence"
                )
                session = APIToolSession(
                    chat_id=chat_id,
                    state="collecting_params",
                    selected_endpoint=endpoint,
                    collected_params={},
                    turn_count=0,
                    max_turns=5,
                    awaiting_continuation=False,
                    detected_language=getattr(request, "_detected_language", "en"),
                )

        # ── Run one loop turn ─────────────────────────────────────────────
        if session_store is None:
            # Without a store the loop cannot persist.
            # so AgenticLoop doesn't crash. The loop will run but state is lost.
            logger.warning(
                f"[{chat_id}] APIToolWorkflow: session store unavailable — "
                f"agentic loop running without persistence"
            )

        loop = self._build_agentic_loop(session_store)  # type: ignore[arg-type]

        result = await loop.run_turn(
            chat_id=chat_id,
            user_message=request.message,
            # On the first turn of a new session (turn_count == 0) we pass an
            # empty history so the extractor only looks at the current message.
            # Full chat history may contain parameter values from a *previous*
            # session that would be falsely re-used for this fresh request.
            # On subsequent turns (turn_count > 0) the history is relevant —
            # the user may refer back to something they said in this session.
            conversation_history=(
                []
                if session.turn_count == 0
                else [
                    {"authorRole": item.authorRole, "message": item.message}
                    for item in (request.conversationHistory or [])
                ]
            ),
            params_schema=endpoint.get("params", []),
            collected_params=session.collected_params,
            turn_count=session.turn_count,
            max_turns=session.max_turns,
            awaiting_continuation=session.awaiting_continuation,
            session_language=session.detected_language,
        )

        # ── Handle result ─────────────────────────────────────────────────
        if result.status == AgenticLoopStatus.COMPLETED:
            logger.info(
                f"[{chat_id}] APIToolWorkflow: all params collected "
                f"(turns={result.turn_count}, params={list(result.collected_params.keys())})"
            )
            if session_store is not None:
                await session_store.delete(chat_id)
            return self._build_completed_response(
                chat_id, endpoint, result.collected_params
            )

        if result.status == AgenticLoopStatus.MAX_TURNS_REACHED:
            logger.info(
                f"[{chat_id}] APIToolWorkflow: max turns reached — deleting session"
            )
            if session_store is not None:
                await session_store.delete(chat_id)
            # Return None to trigger fallback to the RAG workflow
            return None

        # NEEDS_INPUT or AWAITING_CONTINUATION_DECISION — session already saved
        # by the loop; return the question to the user
        logger.info(
            f"[{chat_id}] APIToolWorkflow: asking for more info "
            f"(status={result.status.value}, turn={result.turn_count})"
        )
        return self._build_question_response(chat_id, result.clarifying_question)

    # ------------------------------------------------------------------
    # BaseWorkflow interface
    # ------------------------------------------------------------------

    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[OrchestrationResponse]:
        return await self._run(request, context)

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[AsyncIterator[str]]:
        """Streaming mode — run the loop and wrap the response in SSE frames.

        Clarifying questions and the final params-collected response are both
        short strings, so they are emitted as a single SSE frame + END marker.
        Full token-by-token streaming of the final API response will be added
        when the API caller is implemented.
        """
        if self.orchestration_service is None:
            logger.error(
                f"[{request.chatId}] APIToolWorkflow streaming: orchestration_service not set"
            )
            return None

        response = await self._run(request, context)
        if response is None:
            return None

        orchestration_service = self.orchestration_service
        content = response.content

        async def _stream() -> AsyncIterator[str]:
            yield orchestration_service.format_sse(request.chatId, content)
            yield orchestration_service.format_sse(request.chatId, "END")

        return _stream()
