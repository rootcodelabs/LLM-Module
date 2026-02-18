"""Context workflow executor - Layer 2: Conversation history and greetings."""

from typing import Any, AsyncIterator, Dict, Optional
from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from tool_classifier.base_workflow import BaseWorkflow


class ContextWorkflowExecutor(BaseWorkflow):
    """
    Handles queries answerable from conversation history or greetings (Layer 2).

    This workflow handles two types of queries:
    1. Greetings and conversational pleasantries
       - "Hello", "Good morning", "Thanks", "Goodbye"
    2. Queries referencing conversation history
       - "What did you say earlier?"
       - "Can you repeat that?"
       - "What was the rate you mentioned?"

    Uses LLM-based detection (no regex patterns) for:
    - Semantic greeting detection (multilingual)
    - Context reference detection
    - Answer extraction from conversation history

    Examples:
    - "Tere!" → Friendly greeting response
    - "Hello" → "Hello! How can I help you?"
    - "What was the rate?" (history: "Rate is 1.08") → "The rate was 1.08"

    Implementation Status: SKELETON
    Returns None (triggers fallback to RAG workflow)

    TODO - Full Implementation (Separate Task):
    - Greeting detection using LLM
    - Context availability check using LLM
    - Answer extraction from conversation history
    - Output guardrails for context-based responses
    - Multilingual support (Estonian, English)
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

        TODO: Implement context workflow logic:
        1. Check if query is a greeting using LLM
           - If yes: Generate appropriate greeting response
        2. If not greeting, check conversation history:
           - Get recent history (last 10 turns)
           - Call LLM to check if query can be answered from history
           - If yes: Extract answer from history
        3. Validate answer with output guardrails
        4. Return OrchestrationResponse with context-based answer

        LLM Prompt for Context Check:
        ```
        Conversation History:
        1. User: What's the exchange rate?
        2. Bot: EUR/USD rate is 1.08
        3. User: Thanks

        Current Query: "What was the rate?"

        Can this be answered from history? If yes, provide answer.
        ```

        Failure scenarios:
        - Not a greeting and no conversation history → return None
        - Cannot answer from history → return None (fallback to RAG)
        - Output guardrails blocked → return None or violation message

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

        TODO: Implement context workflow streaming:
        1. Detect greeting or check conversation history (same as non-streaming)
        2. Get complete answer from history or generate greeting response
        3. Validate with output guardrails (validation-first)
        4. If blocked: yield violation message + END
        5. If allowed: chunk answer and stream token-by-token
        6. Simulate streaming for consistent UX with RAG

        Streaming approach (validation-first):
        ```python
        # Get complete context-based answer
        context_result = await analyze_context(query, history)

        if not context_result.can_answer:
            return None  # Fallback to RAG

        # Validate BEFORE streaming
        is_safe = await guardrails.check_output_async(context_result.answer)
        if not is_safe:
            yield format_sse(chatId, VIOLATION_MESSAGE)
            yield format_sse(chatId, "END")
            return

        # Stream validated answer
        for chunk in split_into_tokens(context_result.answer, chunk_size=5):
            yield format_sse(chatId, chunk)
            await asyncio.sleep(0.01)
        yield format_sse(chatId, "END")
        ```

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
