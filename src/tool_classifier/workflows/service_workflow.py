"""Service workflow executor - Layer 1: External service/API calls."""

from typing import Any, AsyncIterator, Dict, Optional
from loguru import logger

from models.request_models import OrchestrationRequest, OrchestrationResponse
from tool_classifier.base_workflow import BaseWorkflow


class ServiceWorkflowExecutor(BaseWorkflow):
    """
    Executes external service calls via Ruuter endpoints (Layer 1).

    This workflow handles queries that require calling external government
    services or APIs. It performs:
    1. Service discovery (semantic search if >50 services)
    2. Intent detection using LLM
    3. Entity extraction from query
    4. Service validation against database
    5. External API call via Ruuter
    6. Output guardrails validation

    Examples of Service queries:
    - "What's the EUR to USD exchange rate?"
    - "Check my document status"
    - "Submit a tax declaration"

    Implementation Status: SKELETON
    Returns None (triggers fallback to Context workflow)

    TODO - Full Implementation (Separate Task):
    - Service discovery logic (Qdrant semantic search)
    - Intent detection (LLM-based)
    - Entity extraction and transformation
    - Service validation (database lookup)
    - Ruuter API integration
    - Output guardrails for service responses
    """

    def __init__(self, llm_manager: Any):
        """
        Initialize service workflow executor.

        Args:
            llm_manager: LLM manager for intent detection
        """
        self.llm_manager = llm_manager
        logger.info("Service workflow executor initialized (skeleton)")

    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[OrchestrationResponse]:
        """
        Execute service workflow in non-streaming mode.

        TODO: Implement service workflow logic:
        1. Extract service metadata from context (service_id, intent, entities)
        2. Validate service exists and is active in database
        3. Transform entities to array format for service call
        4. Call Ruuter endpoint: POST {RUUTER_BASE_URL}/services/active{ServiceName}
        5. Validate response with output guardrails
        6. Return OrchestrationResponse with service result

        Failure scenarios:
        - No service_id in context → return None (fallback to Context)
        - Service not found/inactive → return None (fallback to Context)
        - Service call timeout → return error response
        - Output guardrails blocked → return violation response or None

        Args:
            request: Orchestration request with user query
            context: Metadata with service_id, intent, entities

        Returns:
            OrchestrationResponse with service result or None to fallback
        """
        logger.debug(
            f"[{request.chatId}] Service workflow execute_async called "
            f"(not implemented - returning None)"
        )

        # TODO: Implement service workflow logic here
        # For now, return None to trigger fallback to next layer
        return None

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[AsyncIterator[str]]:
        """
        Execute service workflow in streaming mode.

        TODO: Implement service workflow streaming:
        1. Execute service call (same as non-streaming)
        2. Get complete service response
        3. Validate with output guardrails (validation-first)
        4. If blocked: yield violation message + END
        5. If allowed: chunk response and stream token-by-token
        6. Simulate streaming for consistent UX with RAG

        Streaming approach (validation-first):
        ```python
        # Get complete response
        service_response = await call_service(...)

        # Validate BEFORE streaming
        is_safe = await guardrails.check_output_async(service_response)
        if not is_safe:
            yield format_sse(chatId, VIOLATION_MESSAGE)
            yield format_sse(chatId, "END")
            return

        # Stream validated response
        for chunk in split_into_tokens(service_response, chunk_size=5):
            yield format_sse(chatId, chunk)
            await asyncio.sleep(0.01)
        yield format_sse(chatId, "END")
        ```

        Args:
            request: Orchestration request with user query
            context: Metadata with service_id, intent, entities

        Returns:
            AsyncIterator yielding SSE strings or None to fallback
        """
        logger.debug(
            f"[{request.chatId}] Service workflow execute_streaming called "
            f"(not implemented - returning None)"
        )

        # TODO: Implement service streaming logic here
        # For now, return None to trigger fallback to next layer
        return None
