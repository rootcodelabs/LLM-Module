"""Main tool classifier for workflow routing."""

from typing import Any, AsyncIterator, Dict, List, Literal, Union, overload
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

        Implements layer-wise classification logic:
        1. Check if SERVICE workflow can handle (intent detection)
        2. Check if CONTEXT workflow can handle (greeting/history check)
        3. Default to RAG workflow (knowledge retrieval)

        Args:
            query: User's query string
            conversation_history: List of previous conversation messages
            language: Detected language code (e.g., 'en', 'et')

        Returns:
            ClassificationResult indicating which workflow to use

        Note:
            In this skeleton, always defaults to RAG. Full implementation
            will add Layer 1 and Layer 2 logic in separate tasks.
        """
        logger.info(f"Classifying query: {query[:100]}...")

        # TODO: LAYER 1 - SERVICE WORKFLOW DETECTION
        # Implementation task: Service workflow implementation
        # Logic:
        # 1. Count active services in database
        # 2. If count > 50: Use Qdrant semantic search for top 20 services
        # 3. If count <= 50: Use all services
        # 4. Call LLM to detect intent and extract entities
        # 5. If intent detected and service valid: return SERVICE classification
        # Example:
        #   service_check = await self._check_service_layer(query, language)
        #   if service_check.can_handle:
        #       return ClassificationResult(
        #           workflow=WorkflowType.SERVICE,
        #           confidence=service_check.confidence,
        #           metadata=service_check.metadata,
        #           reasoning="Service intent detected"
        #       )

        # TODO: LAYER 2 - CONTEXT WORKFLOW DETECTION
        # Implementation task: Context workflow implementation
        # Logic:
        # 1. Check if query is a greeting using LLM
        # 2. If greeting: return CONTEXT classification
        # 3. If conversation_history exists: Check if query references history
        # 4. Call LLM to determine if history contains answer
        # 5. If can answer from history: return CONTEXT classification
        # Example:
        #   context_check = await self._check_context_layer(
        #       query, conversation_history, language
        #   )
        #   if context_check.can_handle:
        #       return ClassificationResult(
        #           workflow=WorkflowType.CONTEXT,
        #           confidence=context_check.confidence,
        #           metadata=context_check.metadata,
        #           reasoning="Greeting or answerable from history"
        #       )

        # LAYER 3 - RAG WORKFLOW (DEFAULT)
        # Always defaults to RAG for now
        # RAG workflow will handle the query or return OOD if no chunks found
        logger.info("Defaulting to RAG workflow (Layers 1-2 not implemented)")
        return ClassificationResult(
            workflow=WorkflowType.RAG,
            confidence=1.0,
            metadata={},
            reasoning="Default to RAG workflow (service and context layers not implemented)",
        )

    @overload
    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: Literal[False] = False,
    ) -> OrchestrationResponse: ...

    @overload
    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: Literal[True],
    ) -> AsyncIterator[str]: ...

    async def route_to_workflow(
        self,
        classification: ClassificationResult,
        request: OrchestrationRequest,
        is_streaming: bool = False,
    ) -> Union[OrchestrationResponse, AsyncIterator[str]]:
        """
        Route request to appropriate workflow based on classification.

        Implements fallback chain: If a workflow returns None, tries the next layer.
        This ensures queries always get handled, even if primary workflow fails.

        Args:
            classification: Classification result from classify()
            request: Original orchestration request
            is_streaming: Whether to use streaming mode (for /orchestrate/stream)

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
            )
        else:
            # NON-STREAMING MODE: For /orchestrate and /orchestrate/test endpoints
            return await self._execute_with_fallback_async(
                workflow=workflow,
                request=request,
                context=classification.metadata,
                start_layer=classification.workflow,
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
    ) -> OrchestrationResponse:
        """
        Execute workflow with fallback to subsequent layers (non-streaming).

        TODO: Implement full fallback chain logic
        Currently just executes the primary workflow.

        Full implementation should:
        1. Try primary workflow
        2. If returns None, try next layer in WORKFLOW_LAYER_ORDER
        3. Continue until workflow returns non-None result
        4. OOD workflow always returns result (never None)
        """
        chat_id = request.chatId
        workflow_name = WORKFLOW_DISPLAY_NAMES.get(start_layer, start_layer.value)

        logger.info(f"[{chat_id}] Executing {workflow_name} (non-streaming)")

        try:
            result = await workflow.execute_async(request, context)

            if result is not None:
                logger.info(f"[{chat_id}] {workflow_name} handled successfully")
                return result

            # TODO: Implement fallback to next layer
            # For now, if workflow returns None, call RAG as fallback
            logger.warning(
                f"[{chat_id}] {workflow_name} returned None, "
                f"falling back to RAG workflow"
            )
            rag_result = await self.rag_workflow.execute_async(request, {})
            if rag_result is not None:
                return rag_result
            else:
                # This should never happen since RAG always returns a result
                # But handle gracefully
                raise RuntimeError("RAG workflow returned None unexpectedly")

        except Exception as e:
            logger.error(f"[{chat_id}] Error executing {workflow_name}: {e}")
            # Fallback to RAG on error
            logger.info(f"[{chat_id}] Falling back to RAG due to error")
            rag_result = await self.rag_workflow.execute_async(request, {})
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
    ) -> AsyncIterator[str]:
        """
        Execute workflow with fallback to subsequent layers (streaming).

        TODO: Implement full fallback chain logic
        Currently just executes the primary workflow.

        Full implementation should:
        1. Try primary workflow
        2. If returns None, try next layer in WORKFLOW_LAYER_ORDER
        3. Stream from the first workflow that returns non-None
        4. OOD workflow always returns result (never None)
        """
        chat_id = request.chatId
        workflow_name = WORKFLOW_DISPLAY_NAMES.get(start_layer, start_layer.value)

        logger.info(f"[{chat_id}] Executing {workflow_name} (streaming)")

        try:
            result = await workflow.execute_streaming(request, context)

            if result is not None:
                logger.info(f"[{chat_id}] {workflow_name} streaming started")
                async for chunk in result:
                    yield chunk
                return

            # TODO: Implement fullback to next layer
            # For now, if workflow returns None, call RAG as fallback
            logger.warning(
                f"[{chat_id}] {workflow_name} returned None, "
                f"falling back to RAG workflow streaming"
            )
            streaming_result = await self.rag_workflow.execute_streaming(request, {})
            if streaming_result is not None:
                async for chunk in streaming_result:
                    yield chunk
            else:
                raise RuntimeError("RAG workflow returned None unexpectedly")

        except Exception as e:
            logger.error(f"[{chat_id}] Error executing {workflow_name} streaming: {e}")
            # Fallback to RAG on error
            logger.info(f"[{chat_id}] Falling back to RAG streaming due to error")
            streaming_result = await self.rag_workflow.execute_streaming(request, {})
            if streaming_result is not None:
                async for chunk in streaming_result:
                    yield chunk
            else:
                raise RuntimeError("RAG workflow returned None unexpectedly")
