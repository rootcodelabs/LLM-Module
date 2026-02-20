"""Context workflow executor - Layer 2: Conversation history and greetings."""

from typing import Any, AsyncIterator, Dict, Optional
from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from tool_classifier.base_workflow import BaseWorkflow


class ContextWorkflowExecutor(BaseWorkflow):
    """
    Handles greetings and conversation history queries (Layer 2).

    Detects:
    - Greetings: "Hello", "Thanks", "Goodbye"
    - History references: "What did you say earlier?", "Can you repeat that?"

    Uses LLM for semantic detection (multilingual), no regex patterns.

    Status: SKELETON - Returns None (fallback to RAG)
    TODO: Implement greeting/context detection, answer extraction, guardrails
    """

    def __init__(self, llm_manager: Any):
        """
        Initialize context workflow executor.

        Args:
            llm_manager: LLM manager for context analysis
        """
        self.llm_manager = llm_manager
        logger.info("Context workflow executor initialized (skeleton)")

    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[OrchestrationResponse]:
        """
        Execute context workflow in non-streaming mode.

        TODO: Check greeting (LLM) → generate response, OR check history (last 10 turns)
        → extract answer → validate with guardrails. Return None if cannot answer.

        Args:
            request: Orchestration request with user query and history
            context: Metadata with is_greeting, can_answer_from_history flags

        Returns:
            OrchestrationResponse with context-based answer or None to fallback
        """
        logger.debug(
            f"[{request.chatId}] Context workflow execute_async called "
            f"(not implemented - returning None)"
        )

        # TODO: Implement context workflow logic here
        # For now, return None to trigger fallback to next layer (RAG)
        return None

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[AsyncIterator[str]]:
        """
        Execute context workflow in streaming mode.

        TODO: Get answer (greeting/history) → validate BEFORE streaming → chunk and
        yield as SSE. Return None if cannot answer.

        Args:
            request: Orchestration request with user query and history
            context: Metadata with is_greeting, can_answer_from_history flags

        Returns:
            AsyncIterator yielding SSE strings or None to fallback
        """
        logger.debug(
            f"[{request.chatId}] Context workflow execute_streaming called "
            f"(not implemented - returning None)"
        )

        # TODO: Implement context streaming logic here
        # For now, return None to trigger fallback to next layer (RAG)
        return None
