"""API Tool Calling Workflow Executor — Layer 2 of the classification chain."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from models.session_models import APIToolSession
from tool_classifier.agentic_loop import AgenticLoop
from tool_classifier.api_caller import APICaller
from tool_classifier.api_response_formatter import APIResponseFormatterModule
from tool_classifier.base_workflow import BaseWorkflow
from tool_classifier.enums import AgenticLoopStatus
from tool_classifier.param_extractor import ParamExtractionModule


@dataclass
class _LoopStep:
    """Shared result type from :meth:`APIToolWorkflowExecutor._compute_loop_step`.

    ``kind`` drives both the sync and streaming execution paths:

    * ``"api_call"``  — all params collected; call the external API and format.
    * ``"question"``  — agentic loop needs more input; return ``question`` to user.
    * ``"fallback"``  — nothing to do; caller should fall back to RAG.
    """

    kind: Literal["api_call", "question", "fallback"]
    chat_id: str = ""
    endpoint: Dict[str, Any] = field(default_factory=dict)
    collected_params: Dict[str, Any] = field(default_factory=dict)
    detected_language: str = "en"
    user_query: str = ""
    question: str = ""
    question_tokens: List[str] = field(default_factory=list)


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

    When all required params are collected (COMPLETED) the executor calls the
    external API via :class:`APICaller` and formats the raw response into
    natural-language using :class:`APIResponseFormatterModule`. The formatted
    answer is returned directly to the user.
    """

    def __init__(self, orchestration_service: Optional[Any] = None) -> None:
        self.orchestration_service = orchestration_service
        self._api_caller = APICaller()
        self._formatter = APIResponseFormatterModule()

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

    async def _execute_api_and_format(
        self,
        chat_id: str,
        endpoint: Dict[str, Any],
        collected_params: Dict[str, Any],
        user_query: str,
        detected_language: str,
    ) -> OrchestrationResponse:
        """Call the external API with collected params and return a formatted response.

        On success, the raw API response is converted to natural language by
        :class:`APIResponseFormatterModule`.
        On any failure the localized error message is returned directly to the user.
        """
        url = endpoint.get("url", "")
        method = endpoint.get("method", "GET")
        description = endpoint.get("description", "")

        logger.info(
            f"[{chat_id}] APIToolWorkflow: calling API "
            f"{method} {url} with params={list(collected_params.keys())}"
        )

        api_result = await self._api_caller.call(
            url=url,
            method=method,
            params=collected_params,
            language=detected_language,
        )

        if api_result.success:
            logger.info(
                f"[{chat_id}] APIToolWorkflow: API call succeeded "
                f"(status={api_result.status_code})"
            )
            content = await asyncio.to_thread(
                self._formatter.forward,
                user_query=user_query,
                api_response=api_result.response_data,
                endpoint_description=description,
                detected_language=detected_language,
            )
        else:
            logger.warning(
                f"[{chat_id}] APIToolWorkflow: API call failed "
                f"(status={api_result.status_code}, error={api_result.error!r})"
            )
            content = api_result.error or ""

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

    async def _compute_loop_step(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> _LoopStep:
        """Run one agentic loop turn and return a tagged outcome.

        This is the single source of truth for session management and loop logic.
        Both the sync (:meth:`execute_async`) and streaming (:meth:`execute_streaming`)
        paths call this method and then handle the result in their own way:

        * ``"api_call"``  → call API + format response (blocking or streaming)
        * ``"question"``  → return clarifying question to user
        * ``"fallback"``  → no valid state; caller falls back to RAG
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
                logger.warning(
                    f"[{chat_id}] APIToolWorkflow: session has no endpoint — deleting"
                )
                if session_store is not None:
                    await session_store.delete(chat_id)
                return _LoopStep(kind="fallback", chat_id=chat_id)

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
                return _LoopStep(kind="fallback", chat_id=chat_id)

            params_schema: List[Dict[str, Any]] = endpoint.get("params", [])

            # Fast path: no required params — call API immediately
            if not self._required_params(params_schema):
                logger.info(
                    f"[{chat_id}] APIToolWorkflow: endpoint {endpoint.get('name')!r} "
                    f"has no required params — fast path"
                )
                return _LoopStep(
                    kind="api_call",
                    chat_id=chat_id,
                    endpoint=endpoint,
                    collected_params={},
                    detected_language=getattr(request, "_detected_language", "en"),
                    user_query=request.message,
                )

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
                    original_query=request.message,
                )
                await session_store.save(new_session)
                session = new_session
            else:
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
                    original_query=request.message,
                )

        # ── Run one loop turn ─────────────────────────────────────────────
        if session_store is None:
            logger.warning(
                f"[{chat_id}] APIToolWorkflow: session store unavailable — "
                f"agentic loop running without persistence"
            )

        loop = self._build_agentic_loop(session_store)  # type: ignore[arg-type]

        result, question_tokens = await loop.stream_run_turn(
            chat_id=chat_id,
            user_message=request.message,
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

        # ── Translate result into a _LoopStep ─────────────────────────────
        if result.status == AgenticLoopStatus.COMPLETED:
            logger.info(
                f"[{chat_id}] APIToolWorkflow: all params collected "
                f"(turns={result.turn_count}, params={list(result.collected_params.keys())})"
            )
            if session_store is not None:
                await session_store.delete(chat_id)
            return _LoopStep(
                kind="api_call",
                chat_id=chat_id,
                endpoint=endpoint,
                collected_params=result.collected_params,
                detected_language=session.detected_language,
                user_query=session.original_query or request.message,
            )

        if result.status == AgenticLoopStatus.MAX_TURNS_REACHED:
            logger.info(
                f"[{chat_id}] APIToolWorkflow: max turns reached — deleting session"
            )
            if session_store is not None:
                await session_store.delete(chat_id)
            return _LoopStep(kind="fallback", chat_id=chat_id)

        # NEEDS_INPUT or AWAITING_CONTINUATION_DECISION
        logger.info(
            f"[{chat_id}] APIToolWorkflow: asking for more info "
            f"(status={result.status.value}, turn={result.turn_count})"
        )
        return _LoopStep(
            kind="question",
            chat_id=chat_id,
            question=result.clarifying_question,
            question_tokens=question_tokens,
        )

    async def _run(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[OrchestrationResponse]:
        """Blocking execution path — delegates to :meth:`_compute_loop_step`."""
        step = await self._compute_loop_step(request, context)

        if step.kind == "fallback":
            return None

        if step.kind == "question":
            return self._build_question_response(step.chat_id, step.question)

        # api_call — blocking
        return await self._execute_api_and_format(
            chat_id=step.chat_id,
            endpoint=step.endpoint,
            collected_params=step.collected_params,
            user_query=step.user_query,
            detected_language=step.detected_language,
        )

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

    async def _stream_api_and_format(
        self,
        chat_id: str,
        endpoint: Dict[str, Any],
        collected_params: Dict[str, Any],
        user_query: str,
        detected_language: str,
        orchestration_service: Any,
    ) -> AsyncIterator[str]:
        """Call the external API and stream the formatted response token by token.

        Clarifying questions are short and do not need token streaming; they are
        yielded as a single SSE frame.
        """
        url = endpoint.get("url", "")
        method = endpoint.get("method", "GET")
        description = endpoint.get("description", "")

        logger.info(
            f"[{chat_id}] APIToolWorkflow (streaming): calling API "
            f"{method} {url} with params={list(collected_params.keys())}"
        )

        api_result = await self._api_caller.call(
            url=url,
            method=method,
            params=collected_params,
            language=detected_language,
        )

        if api_result.success:
            logger.info(
                f"[{chat_id}] APIToolWorkflow (streaming): API call succeeded "
                f"(status={api_result.status_code}), streaming formatted response"
            )
            async for token in self._formatter.stream_forward(
                user_query=user_query,
                api_response=api_result.response_data,
                endpoint_description=description,
                detected_language=detected_language,
            ):
                yield orchestration_service.format_sse(chat_id, token)
        else:
            logger.warning(
                f"[{chat_id}] APIToolWorkflow (streaming): API call failed "
                f"(status={api_result.status_code}, error={api_result.error!r})"
            )
            yield orchestration_service.format_sse(chat_id, api_result.error or "")

        yield orchestration_service.format_sse(chat_id, "END")

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[AsyncIterator[str]]:
        """Streaming mode — run the agentic loop and stream the response token by token.

        Clarifying questions (NEEDS_INPUT / AWAITING_CONTINUATION) are short; they
        are emitted as a single SSE frame followed by END — same as before.

        Final API responses (COMPLETED / fast-path) are streamed word-by-word via
        DSPy native streaming on the ``formatted_answer`` field.
        """
        if self.orchestration_service is None:
            logger.error(
                f"[{request.chatId}] APIToolWorkflow streaming: orchestration_service not set"
            )
            return None

        step = await self._compute_loop_step(request, context)

        if step.kind == "fallback":
            return None

        orchestration_service = self.orchestration_service

        if step.kind == "question":

            async def _stream_question() -> AsyncIterator[str]:
                for token in step.question_tokens or [step.question]:
                    yield orchestration_service.format_sse(step.chat_id, token)
                yield orchestration_service.format_sse(step.chat_id, "END")

            return _stream_question()

        # api_call — stream the LLM-formatted answer token by token
        return self._stream_api_and_format(
            chat_id=step.chat_id,
            endpoint=step.endpoint,
            collected_params=step.collected_params,
            user_query=step.user_query,
            detected_language=step.detected_language,
            orchestration_service=orchestration_service,
        )
