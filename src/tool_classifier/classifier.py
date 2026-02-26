"""Main tool classifier for workflow routing."""

from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Union, overload
from loguru import logger

from models.request_models import (
    ConversationItem,
    OrchestrationRequest,
    OrchestrationResponse,
)
from tool_classifier.enums import WorkflowType, WORKFLOW_DISPLAY_NAMES
from tool_classifier.models import ClassificationResult
from tool_classifier.workflows import (
    ServiceWorkflowExecutor,
    ContextWorkflowExecutor,
    RAGWorkflowExecutor,
    OODWorkflowExecutor,
)


class ToolClassifier:
    """
    Main classifier that determines which workflow should handle user queries.

    Implements a layer-wise filtering approach:
    Layer 1: Service Workflow → External API calls
    Layer 2: Context Workflow → Conversation history/greetings
    Layer 3: RAG Workflow → Knowledge base retrieval
    Layer 4: OOD Workflow → Out-of-domain fallback

    Each layer is tried in sequence. If a layer cannot handle the query
    (returns None), the classifier falls back to the next layer.

    Architecture:
    - Strategy Pattern: Each workflow is a pluggable strategy
    - Chain of Responsibility: Layers form a fallback chain
    - Dependency Injection: LLM manager and connections injected from main service
    """

    def __init__(
        self,
        llm_manager: Any,
        orchestration_service: Any,
    ):
        """
        Initialize tool classifier with required dependencies.

        Args:
            llm_manager: LLM manager for making LLM calls (intent detection, context check)
            orchestration_service: Reference to main orchestration service (for RAG workflow)
        """
        self.llm_manager = llm_manager
        self.orchestration_service = orchestration_service

        # Initialize workflow executors
        self.service_workflow = ServiceWorkflowExecutor(
            llm_manager=llm_manager,
            orchestration_service=orchestration_service,
        )
        self.context_workflow = ContextWorkflowExecutor(
            llm_manager=llm_manager,
        )
        self.rag_workflow = RAGWorkflowExecutor(
            orchestration_service=orchestration_service,
        )
        self.ood_workflow = OODWorkflowExecutor()

        logger.info("Tool classifier initialized with all workflow executors")

    async def classify(
        self,
        query: str,
        conversation_history: List[ConversationItem],
        language: str,
    ) -> ClassificationResult:
        """
        Classify a user query to determine which workflow should handle it.

        Implements layer-wise classification logic with fallback chain:
        1. SERVICE workflow (external API calls)
        2. CONTEXT workflow (greetings/conversation history)
        3. RAG workflow (knowledge base retrieval)
        4. OOD workflow (out-of-domain)

        Args:
            query: User's query string
            conversation_history: List of previous conversation messages
            language: Detected language code (e.g., 'en', 'et')

        Returns:
            ClassificationResult indicating which workflow to use
        """
        logger.info(f"Classifying query: {query[:100]}...")

        logger.info("Starting layer-wise fallback: ")
        return ClassificationResult(
            workflow=WorkflowType.SERVICE,
            confidence=1.0,
            metadata={},
            reasoning="Start with Service workflow - will cascade through layers",
        )

    @overload
    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: Literal[False] = False,
        time_metric: Optional[Dict[str, float]] = None,
    ) -> OrchestrationResponse: ...

    @overload
    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: Literal[True],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> AsyncIterator[str]: ...

    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: bool = False,
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Union[OrchestrationResponse, AsyncIterator[str]]:
        """
        Route request to appropriate workflow based on classification.

        Implements fallback chain: If a workflow returns None, tries the next layer.
        This ensures queries always get handled, even if primary workflow fails.

        Args:
            classification: Classification result from classify()
            request: Original orchestration request
            is_streaming: Whether to use streaming mode (for /orchestrate/stream)
            time_metric: Optional timing dictionary for workflow step tracking

        Returns:
            OrchestrationResponse for non-streaming mode
            AsyncIterator[str] for streaming mode

        Fallback Chain:
            SERVICE → CONTEXT → RAG → OOD
            Each layer returns None if it cannot handle, triggering next layer.
        """
        chat_id = request.chatId
        workflow_name = WORKFLOW_DISPLAY_NAMES.get(
            classification.workflow, classification.workflow.value
        )

        logger.info(
            f"[{chat_id}] Routing to {workflow_name} "
            f"(streaming: {is_streaming}, confidence: {classification.confidence:.2f})"
        )

        # Get the workflow executor
        workflow = self._get_workflow_executor(classification.workflow)

        if is_streaming:
            # STREAMING MODE: For /orchestrate/stream endpoint
            # Return the async iterator directly
            return self._execute_with_fallback_streaming(
                workflow=workflow,
                request=request,
                context=classification.metadata,
                start_layer=classification.workflow,
                time_metric=time_metric,
            )
        else:
            # NON-STREAMING MODE: For /orchestrate and /orchestrate/test endpoints
            return await self._execute_with_fallback_async(
                workflow=workflow,
                request=request,
                context=classification.metadata,
                start_layer=classification.workflow,
                time_metric=time_metric,
            )

    def _get_workflow_executor(self, workflow_type: WorkflowType) -> Any:
        """Get workflow executor instance for given workflow type."""
        workflow_map = {
            WorkflowType.SERVICE: self.service_workflow,
            WorkflowType.CONTEXT: self.context_workflow,
            WorkflowType.RAG: self.rag_workflow,
            WorkflowType.OOD: self.ood_workflow,
        }
        return workflow_map[workflow_type]

    async def _execute_with_fallback_async(
        self,
        workflow: Any,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        start_layer: WorkflowType,
        time_metric: Optional[Dict[str, float]] = None,
    ) -> OrchestrationResponse:
        """
        Execute workflow with fallback to subsequent layers (non-streaming).

        Implementation:
        1. Try primary workflow
        2. If returns None, try next layer in WORKFLOW_LAYER_ORDER
        3. Continue until workflow returns non-None result
        4. OOD workflow always returns result (never None)

        Args:
            workflow: Primary workflow executor
            request: Orchestration request
            context: Workflow context/metadata
            start_layer: Starting workflow type
            time_metric: Optional timing dictionary for tracking
        """
        chat_id = request.chatId
        workflow_name = WORKFLOW_DISPLAY_NAMES.get(start_layer, start_layer.value)

        logger.info(f"[{chat_id}] Executing {workflow_name} (non-streaming)")

        try:
            result = await workflow.execute_async(request, context, time_metric)

            if result is not None:
                logger.info(f"[{chat_id}] {workflow_name} handled successfully")
                return result

            # Implement layer-wise fallback chain
            logger.info(
                f"[{chat_id}] {workflow_name} returned None, "
                f"trying next layer in fallback chain"
            )

            # Get the layer order starting from current layer
            from tool_classifier.enums import WORKFLOW_LAYER_ORDER

            current_index = WORKFLOW_LAYER_ORDER.index(start_layer)
            remaining_layers = WORKFLOW_LAYER_ORDER[current_index + 1 :]

            # Try each subsequent layer in order
            for next_layer in remaining_layers:
                next_workflow = self._get_workflow_executor(next_layer)
                next_name = WORKFLOW_DISPLAY_NAMES.get(next_layer, next_layer.value)

                logger.info(
                    f"[{chat_id}] Falling back to {next_name} "
                    f"(Layer {WORKFLOW_LAYER_ORDER.index(next_layer) + 1})"
                )

                result = await next_workflow.execute_async(request, {}, time_metric)

                if result is not None:
                    logger.info(f"[{chat_id}] {next_name} handled successfully")
                    return result

                logger.info(f"[{chat_id}] {next_name} returned None, continuing...")
                current_index += 1

            # This should never happen since RAG/OOD should always return result
            raise RuntimeError("All workflows returned None (unexpected)")

        except Exception as e:
            logger.error(f"[{chat_id}] Error executing {workflow_name}: {e}")
            # Fallback to RAG on error
            logger.info(f"[{chat_id}] Falling back to RAG due to error")
            rag_result = await self.rag_workflow.execute_async(request, {}, time_metric)
            if rag_result is not None:
                return rag_result
            else:
                raise RuntimeError("RAG workflow returned None unexpectedly")

    async def _execute_with_fallback_streaming(
        self,
        workflow: Any,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        start_layer: WorkflowType,
        time_metric: Optional[Dict[str, float]] = None,
    ) -> AsyncIterator[str]:
        """
        Execute workflow with fallback to subsequent layers (streaming).

        Implementation:
        1. Try primary workflow
        2. If returns None, try next layer in WORKFLOW_LAYER_ORDER
        3. Stream from the first workflow that returns non-None
        4. OOD workflow always returns result (never None)

        Args:
            workflow: Primary workflow executor
            request: Orchestration request
            context: Workflow context/metadata
            start_layer: Starting workflow type
            time_metric: Optional timing dictionary for tracking
        """
        chat_id = request.chatId
        workflow_name = WORKFLOW_DISPLAY_NAMES.get(start_layer, start_layer.value)

        logger.info(f"[{chat_id}] Executing {workflow_name} (streaming)")

        try:
            result = await workflow.execute_streaming(request, context, time_metric)

            if result is not None:
                logger.info(f"[{chat_id}] {workflow_name} streaming started")
                async for chunk in result:
                    yield chunk
                return

            # Implement layer-wise fallback chain for streaming
            logger.info(
                f"[{chat_id}] {workflow_name} returned None, "
                f"trying next layer in fallback chain"
            )

            # Get the layer order starting from current layer
            from tool_classifier.enums import WORKFLOW_LAYER_ORDER

            current_index = WORKFLOW_LAYER_ORDER.index(start_layer)
            remaining_layers = WORKFLOW_LAYER_ORDER[current_index + 1 :]

            # Try each subsequent layer in order
            for next_layer in remaining_layers:
                next_workflow = self._get_workflow_executor(next_layer)
                next_name = WORKFLOW_DISPLAY_NAMES.get(next_layer, next_layer.value)

                layer_number = WORKFLOW_LAYER_ORDER.index(next_layer) + 1
                logger.info(
                    f"[{chat_id}] Falling back to {next_name} streaming "
                    f"(Layer {layer_number})"
                )

                result = await next_workflow.execute_streaming(request, {}, time_metric)

                if result is not None:
                    logger.info(f"[{chat_id}] {next_name} streaming started")
                    async for chunk in result:
                        yield chunk
                    return

                logger.info(f"[{chat_id}] {next_name} returned None, continuing...")
                current_index += 1

            # This should never happen
            raise RuntimeError("All workflows returned None in streaming (unexpected)")

        except Exception as e:
            logger.error(f"[{chat_id}] Error executing {workflow_name} streaming: {e}")
            # Fallback to RAG on error
            logger.info(f"[{chat_id}] Falling back to RAG streaming due to error")
            streaming_result = await self.rag_workflow.execute_streaming(
                request, {}, time_metric
            )
            if streaming_result is not None:
                async for chunk in streaming_result:
                    yield chunk
            else:
                raise RuntimeError("RAG workflow returned None unexpectedly")
