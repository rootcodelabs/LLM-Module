"""API Tool Calling Workflow Executor — Layer 2 of the classification chain.

This is the Task 4.1 minimal implementation that surfaces the matched API endpoint
to the user. The full agentic loop (parameter collection → API call → response
formatting) will be implemented in Task 10.
"""

from typing import Any, AsyncIterator, Dict, Optional

from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from tool_classifier.base_workflow import BaseWorkflow


class APIToolWorkflowExecutor(BaseWorkflow):
    """Executes API Tool Calling workflow (Layer 2).

    Handles queries that matched an API endpoint in api_tool_collection.
    Reads the matched endpoint from context (populated by ToolClassifier.classify())
    and returns it as a response.

    Task 10 will replace the placeholder response body with the full agentic loop:
    session management → parameter collection → external API call → response formatting.
    """

    def __init__(self, orchestration_service: Optional[Any] = None) -> None:
        """Initialize API tool calling workflow.

        Args:
            orchestration_service: Reference to LLMOrchestrationService — required
                for streaming mode (format_sse). Optional for non-streaming.
        """
        self.orchestration_service = orchestration_service

    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[OrchestrationResponse]:
        """Execute API tool calling workflow in non-streaming mode.

        Args:
            request: Orchestration request.
            context: Must contain "matched_endpoint" dict from APISemanticSearcher.
            time_metric: Optional timing dict for step tracking.

        Returns:
            OrchestrationResponse with matched endpoint info, or None if no
            endpoint in context (triggers fallback to next layer).
        """
        chat_id = request.chatId
        endpoint = context.get("matched_endpoint")

        if not endpoint:
            logger.warning(
                f"[{chat_id}] APIToolWorkflow: no matched_endpoint in context — falling back"
            )
            return None

        name = endpoint.get("name", "unknown")
        description = endpoint.get("description", "")
        url = endpoint.get("url", "N/A")
        confidence = endpoint.get("confidence", "medium")
        cosine_score = endpoint.get("cosine_score", 0.0)

        logger.info(
            f"[{chat_id}] APIToolWorkflow: matched endpoint={name!r} "
            f"(confidence={confidence}, cosine={cosine_score:.4f})"
        )

        # TODO (Task 10): Replace with full agentic loop —
        # load/create session → run param extraction → call external API → format response
        content = f"**{name}**: {description}\n\nURL: {url}"

        return OrchestrationResponse(
            chatId=chat_id,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=content,
        )

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[AsyncIterator[str]]:
        """Execute API tool calling workflow in streaming mode.

        Args:
            request: Orchestration request.
            context: Must contain "matched_endpoint" dict from APISemanticSearcher.
            time_metric: Optional timing dict for step tracking.

        Returns:
            AsyncIterator yielding SSE-formatted strings, or None on failure.
        """
        chat_id = request.chatId
        endpoint = context.get("matched_endpoint")

        if not endpoint:
            logger.warning(
                f"[{chat_id}] APIToolWorkflow streaming: no matched_endpoint — falling back"
            )
            return None

        if self.orchestration_service is None:
            logger.error(
                f"[{chat_id}] APIToolWorkflow streaming: orchestration_service not set"
            )
            return None

        name = endpoint.get("name", "unknown")
        description = endpoint.get("description", "")
        url = endpoint.get("url", "N/A")
        confidence = endpoint.get("confidence", "medium")
        cosine_score = endpoint.get("cosine_score", 0.0)

        logger.info(
            f"[{chat_id}] APIToolWorkflow streaming: matched endpoint={name!r} "
            f"(confidence={confidence}, cosine={cosine_score:.4f})"
        )

        # TODO (Task 10): Replace with full agentic loop streaming
        content = f"**{name}**: {description}\n\nURL: {url}"

        orchestration_service = self.orchestration_service

        async def _stream() -> AsyncIterator[str]:
            yield orchestration_service.format_sse(chat_id, content)
            yield orchestration_service.format_sse(chat_id, "END")

        return _stream()
