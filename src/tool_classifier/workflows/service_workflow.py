"""Service workflow executor - Layer 1: External service/API calls."""

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol

import dspy
import httpx
from loguru import logger

from src.utils.cost_utils import get_lm_usage_since

from models.request_models import (
    OrchestrationRequest,
    OrchestrationResponse,
)
from tool_classifier.base_workflow import BaseWorkflow
from tool_classifier.constants import (
    MAX_SERVICES_FOR_LLM_CONTEXT,
    QDRANT_COLLECTION,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_TIMEOUT,
    RAG_SEARCH_RUUTER_PUBLIC,
    RUUTER_BASE_URL,
    SEMANTIC_SEARCH_THRESHOLD,
    SEMANTIC_SEARCH_TOP_K,
    SERVICE_COUNT_THRESHOLD,
    SERVICE_DISCOVERY_TIMEOUT,
)
from tool_classifier.intent_detector import IntentDetectionModule
import time


class LLMServiceProtocol(Protocol):
    """Protocol defining interface for LLM service embedding operations."""

    def create_embeddings_for_indexer(
        self,
        texts: List[str],
        environment: str = "production",
        connection_id: Optional[str] = None,
        batch_size: int = 10,
    ) -> Dict[str, Any]:
        """Create embeddings for text inputs using the configured embedding model.

        Args:
            texts: List of text strings to embed
            environment: Environment for model resolution
            connection_id: Optional connection ID for service selection
            batch_size: Number of texts to process in each batch

        Returns:
            Dictionary containing embeddings list and metadata
        """
        ...

    def format_sse(self, chat_id: str, content: str) -> str:
        """Format content as SSE message.

        Args:
            chat_id: Chat/channel identifier
            content: Content to send (token, "END", error message, etc.)

        Returns:
            SSE-formatted string: "data: {json}\\n\\n"
        """
        ...

    def log_costs(self, costs_metric: Dict[str, Dict[str, Any]]) -> None:
        """Log cost information for tracking.

        Args:
            costs_metric: Dictionary of costs per component
        """
        ...


class ServiceWorkflowExecutor(BaseWorkflow):
    """Executes external service calls via Ruuter endpoints (Layer 1)."""

    def __init__(
        self,
        llm_manager: Any,
        orchestration_service: Optional[LLMServiceProtocol] = None,
    ) -> None:
        """Initialize service workflow executor."""
        self.llm_manager = llm_manager
        self.orchestration_service = orchestration_service

    async def _semantic_search_services(
        self,
        query: str,
        request: OrchestrationRequest,
        chat_id: str,
        top_k: int = SEMANTIC_SEARCH_TOP_K,
    ) -> Optional[List[Dict[str, Any]]]:
        """Search services using semantic search via Qdrant.

        Creates a new httpx.AsyncClient per request to ensure proper resource cleanup.
        This is safe and efficient since semantic search is infrequent (only when many services exist).
        """
        if not self.orchestration_service:
            logger.error(
                f"[{chat_id}] Semantic search unavailable: orchestration service not provided"
            )
            return None

        try:
            # Generate embedding using orchestration service
            embedding_result = self.orchestration_service.create_embeddings_for_indexer(
                texts=[query],
                environment=request.environment,
                connection_id=request.connection_id,
                batch_size=1,
            )

            embeddings = embedding_result.get("embeddings", [])
            if not embeddings or len(embeddings) == 0:
                logger.error(f"[{chat_id}] No embedding returned for query")
                return None

            query_embedding = embeddings[0]

            # Create Qdrant client with proper resource cleanup via context manager
            qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
            async with httpx.AsyncClient(
                base_url=qdrant_url, timeout=QDRANT_TIMEOUT
            ) as client:
                # Verify collection exists and has data
                try:
                    collection_info = await client.get(
                        f"/collections/{QDRANT_COLLECTION}"
                    )
                    if collection_info.status_code == 200:
                        info = collection_info.json()
                        points_count = info.get("result", {}).get("points_count", 0)
                        if points_count == 0:
                            logger.error(f"[{chat_id}] Collection is empty")
                            return None
                except Exception as e:
                    logger.warning(f"[{chat_id}] Could not verify collection: {e}")

                # Search Qdrant collection
                search_payload = {
                    "vector": query_embedding,
                    "limit": top_k,
                    "score_threshold": SEMANTIC_SEARCH_THRESHOLD,
                    "with_payload": True,
                }

                response = await client.post(
                    f"/collections/{QDRANT_COLLECTION}/points/search",
                    json=search_payload,
                )

                if response.status_code != 200:
                    logger.error(
                        f"[{chat_id}] Qdrant search failed: HTTP {response.status_code}"
                    )
                    return None

                search_results = response.json()
                points = search_results.get("result", [])

                if len(points) == 0:
                    logger.warning(
                        f"[{chat_id}] No services matched (threshold={SEMANTIC_SEARCH_THRESHOLD})"
                    )
                    return None

                # Transform Qdrant results to service format
                services: List[Dict[str, Any]] = []
                for point in points:
                    payload = point.get("payload", {})
                    score = float(point.get("score", 0))

                    service = {
                        "serviceId": payload.get("service_id"),
                        "service_id": payload.get("service_id"),
                        "name": payload.get("name"),
                        "description": payload.get("description"),
                        "examples": payload.get("examples", []),
                        "entities": payload.get("entities", []),
                        # Note: endpoint not stored in intent_collections,
                        # will be resolved via database lookup if needed
                        "similarity_score": score,
                    }
                    services.append(service)

                logger.info(
                    f"[{chat_id}] Found {len(services)} services via semantic search"
                )
                return services

        except Exception as e:
            logger.error(f"[{chat_id}] Semantic search failed: {e}", exc_info=True)
            return None

    async def _call_service_discovery(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Call Ruuter endpoint to get services for intent detection."""
        endpoint = f"{RAG_SEARCH_RUUTER_PUBLIC}/services/get-services"

        try:
            async with httpx.AsyncClient(timeout=SERVICE_DISCOVERY_TIMEOUT) as client:
                response = await client.get(endpoint)
                response.raise_for_status()
                data = response.json()
                return data
        except httpx.TimeoutException:
            logger.error(
                f"[{chat_id}] Service discovery timeout after {SERVICE_DISCOVERY_TIMEOUT}s"
            )
            return None
        except httpx.HTTPStatusError as e:
            logger.error(
                f"[{chat_id}] Service discovery HTTP error: {e.response.status_code}"
            )
            return None
        except Exception as e:
            logger.error(f"[{chat_id}] Service discovery failed: {e}", exc_info=True)
            return None

    async def _detect_service_intent(
        self,
        user_query: str,
        services: List[Dict[str, Any]],
        conversation_history: List[Any],
        chat_id: str,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Use DSPy + LLMManager to detect service intent and extract entities.

        Returns:
            Tuple of (intent_result, usage_info):
                - intent_result: Intent detection result dict (or None on error)
                - usage_info: Cost and token usage information
        """
        try:
            # Ensure DSPy is configured with LLMManager
            if self.llm_manager:
                self.llm_manager.ensure_global_config()
            else:
                logger.error(f"[{chat_id}] LLM Manager not available")
                return None, {}

            # Capture history length before LLM call for cost tracking
            lm = dspy.settings.lm
            history_length_before = (
                len(lm.history) if lm and hasattr(lm, "history") else 0
            )

            # Create DSPy module
            intent_module = IntentDetectionModule()

            # Convert conversation history to dict format
            history_dicts = [
                {"authorRole": msg.authorRole, "message": msg.message}
                for msg in conversation_history
                if hasattr(msg, "authorRole") and hasattr(msg, "message")
            ]

            # Call DSPy forward with task-local config
            with self.llm_manager.use_task_local():
                intent_result = intent_module.forward(
                    user_query=user_query,
                    services=services,
                    conversation_history=history_dicts,
                )

            # Extract usage information after LLM call
            usage_info = get_lm_usage_since(history_length_before)

            return intent_result, usage_info

        except Exception as e:
            logger.error(f"[{chat_id}] Intent detection failed: {e}", exc_info=True)
            return None, {}

    def _validate_detected_service(
        self,
        matched_service_id: str,
        services: List[Dict[str, Any]],
        chat_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Validate that detected service exists in active services list."""
        for service in services:
            service_id = service.get("serviceId", service.get("service_id"))
            if service_id == matched_service_id:
                return service

        logger.warning(
            f"[{chat_id}] Service validation failed: '{matched_service_id}' not found"
        )
        return None

    async def _process_intent_detection(
        self,
        services: List[Dict[str, Any]],
        request: OrchestrationRequest,
        chat_id: str,
        context: Dict[str, Any],
        costs_metric: Dict[str, Dict[str, Any]],
    ) -> None:
        """Detect intent, validate service, and populate context.

        This helper method encapsulates the common logic of:
        1. Calling intent detection (LLM)
        2. Tracking costs
        3. Validating matched service
        4. Populating context with service metadata

        Args:
            services: List of services to match against
            request: Orchestration request
            chat_id: Chat ID for logging
            context: Context dict to populate with results
            costs_metric: Dictionary to track LLM costs
        """
        intent_result, intent_usage = await self._detect_service_intent(
            user_query=request.message,
            services=services,
            conversation_history=request.conversationHistory,
            chat_id=chat_id,
        )
        costs_metric["intent_detection"] = intent_usage

        if intent_result and intent_result.get("matched_service_id"):
            service_id = intent_result["matched_service_id"]
            logger.info(f"[{chat_id}] Matched: {service_id}")

            validated_service = self._validate_detected_service(
                matched_service_id=service_id,
                services=services,
                chat_id=chat_id,
            )

            if validated_service:
                context["service_id"] = service_id
                context["confidence"] = intent_result.get("confidence", 0.0)
                context["entities"] = intent_result.get("entities", {})
                context["service_data"] = validated_service

    def _extract_service_metadata(
        self, context: Dict[str, Any], chat_id: str
    ) -> Optional[Dict[str, Any]]:
        """Extract service and entity metadata from context."""
        # Check if service_id exists
        service_id = context.get("service_id")
        if not service_id:
            logger.error(f"[{chat_id}] Missing service_id in context")
            return None

        # Check if service_data exists
        service_data = context.get("service_data")
        if not service_data:
            logger.error(f"[{chat_id}] Missing service_data in context")
            return None

        # Extract entities dict from context (LLM extracted)
        entities_dict = context.get("entities", {})

        # Extract entity schema from service_data (expected order)
        entity_schema = service_data.get("entities", [])
        if entity_schema is None:
            entity_schema = []

        # Extract service name
        service_name = service_data.get("name", service_id)

        # Extract HTTP method (ruuter_type) - defaults to GET if not specified
        ruuter_type = service_data.get("ruuter_type", "GET")

        return {
            "service_id": service_id,
            "service_name": service_name,
            "entities_dict": entities_dict,
            "entity_schema": entity_schema,
            "ruuter_type": ruuter_type,
            "service_data": service_data,
        }

    def _validate_entities(
        self,
        extracted_entities: Dict[str, str],
        service_schema: List[str],
        service_name: str,
        chat_id: str,
    ) -> Dict[str, Any]:
        """
        Validate extracted entities against service schema.

        Args:
            extracted_entities: Entity key-value pairs from LLM
            service_schema: Expected entity keys from database
            service_name: Service name for logging
            chat_id: For logging

        Returns:
            Dict with validation results:
            - is_valid: Overall validation status
            - missing_entities: List of schema entities not extracted
            - extra_entities: List of extracted entities not in schema
            - validation_errors: List of error messages
        """
        missing_entities = []
        extra_entities = []
        validation_errors = []

        # Check for missing entities (in schema but not extracted)
        for schema_key in service_schema:
            if schema_key not in extracted_entities:
                missing_entities.append(schema_key)
            elif extracted_entities[schema_key] == "":
                # Entity extracted but value is empty
                validation_errors.append(f"Entity '{schema_key}' has empty value")

        # Check for extra entities (extracted but not in schema)
        for entity_key in extracted_entities:
            if entity_key not in service_schema:
                extra_entities.append(entity_key)

        # Determine overall validity
        # We consider it valid even with missing entities (will send empty strings)
        # Let the external service validate required parameters
        is_valid = True  # Always true - we proceed with partial entities

        return {
            "is_valid": is_valid,
            "missing_entities": missing_entities,
            "extra_entities": extra_entities,
            "validation_errors": validation_errors,
        }

    def _transform_entities_to_array(
        self, entities_dict: Dict[str, str], entity_order: List[str]
    ) -> List[str]:
        """Transform entity dictionary to ordered array based on service schema."""
        if not entity_order:
            return []

        # Transform to ordered array, filling missing with empty strings
        return [entities_dict.get(key, "") for key in entity_order]

    def _construct_service_endpoint(self, service_name: str, chat_id: str) -> str:
        """Construct the full service endpoint URL for Ruuter."""
        return f"{RUUTER_BASE_URL}/services/active{service_name}"

    def _format_debug_response(
        self,
        service_name: str,
        endpoint_url: str,
        http_method: str,
        entities_array: List[str],
    ) -> str:
        """Format debug information for testing (temporary before Step 7 implementation)."""
        entities_str = ", ".join(f'"{e}"' for e in entities_array)
        return (
            f" Service Validated: {service_name}\n"
            f" Endpoint URL: {endpoint_url}\n"
            f" HTTP Method: {http_method}\n"
            f" Extracted Entities: [{entities_str}]\n\n"
        )

    async def _log_request_details(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        mode: str,
        costs_metric: Dict[str, Dict[str, Any]],
    ) -> None:
        """Log request details and perform service discovery.

        Args:
            request: The orchestration request
            context: Workflow context dictionary
            mode: Execution mode ("streaming" or "non-streaming")
            costs_metric: Dictionary to accumulate cost tracking information
        """
        chat_id = request.chatId
        logger.info(f"[{chat_id}] SERVICE WORKFLOW ({mode}): {request.message}")

        # Service Discovery
        discovery_result = await self._call_service_discovery(chat_id)

        if discovery_result:
            # Extract data from nested response structure
            response_data = discovery_result.get("response", {})
            use_semantic = response_data.get("use_semantic_search", False)
            service_count = response_data.get("service_count", 0)

            # Handle service_count if it's a string or NaN
            if isinstance(service_count, str):
                try:
                    service_count = int(service_count)
                except (ValueError, TypeError):
                    service_count = 0

            services_from_ruuter = response_data.get("services", [])

            # Use semantic search if count > threshold
            if service_count > SERVICE_COUNT_THRESHOLD:
                use_semantic = True

            if use_semantic:
                # Use semantic search to find relevant services
                services = await self._semantic_search_services(
                    query=request.message,
                    request=request,
                    chat_id=chat_id,
                    top_k=SEMANTIC_SEARCH_TOP_K,
                )

                if not services:
                    logger.warning(f"[{chat_id}] Semantic search failed")

                    if services_from_ruuter:
                        services = services_from_ruuter
                    elif service_count <= MAX_SERVICES_FOR_LLM_CONTEXT:
                        fallback_result = await self._call_service_discovery(chat_id)
                        if fallback_result:
                            fallback_data = fallback_result.get("response", {})
                            services = fallback_data.get("services", [])
                        else:
                            services = []
                    else:
                        logger.error(f"[{chat_id}] Too many services ({service_count})")
                        services = []

                if services:
                    await self._process_intent_detection(
                        services=services,
                        request=request,
                        chat_id=chat_id,
                        context=context,
                        costs_metric=costs_metric,
                    )
            else:
                services = response_data.get("services", [])

                if services:
                    await self._process_intent_detection(
                        services=services,
                        request=request,
                        chat_id=chat_id,
                        context=context,
                        costs_metric=costs_metric,
                    )
        else:
            logger.warning(f"[{chat_id}] Service discovery failed")

    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[OrchestrationResponse]:
        """Execute service workflow in non-streaming mode.

        Uses classification metadata from hybrid search:
        - needs_llm_confirmation=False: Skip discovery + intent detection, use matched service
        - needs_llm_confirmation=True: Run LLM intent detection on candidate services only
        - No metadata: Fall back to original discovery flow

        Args:
            request: Orchestration request
            context: Workflow context
            time_metric: Optional timing dictionary for unified tracking
        """

        chat_id = request.chatId

        # Create costs tracking dictionary (follows RAG workflow pattern)
        costs_metric: Dict[str, Dict[str, Any]] = {}
        # Use parent time_metric or create new one
        if time_metric is None:
            time_metric = {}

        # Check if classifier provided hybrid search metadata
        needs_llm_confirmation = context.get("needs_llm_confirmation")

        if needs_llm_confirmation is False:
            # HIGH CONFIDENCE PATH: Classifier matched a service with high confidence
            # Skip service discovery — use hybrid search match directly
            matched_service_id = context.get("matched_service_id")
            matched_service_name = context.get("matched_service_name")
            rrf_score = context.get("rrf_score", 0)

            logger.info(
                f"[{chat_id}] HIGH-CONFIDENCE SERVICE MATCH (non-streaming): "
                f"{matched_service_name} (rrf_score={rrf_score:.6f}) - "
                f"skipping discovery"
            )

            # Get service details from top_results (already retrieved by classifier)
            top_results = context.get("top_results", [])
            if top_results:
                matched = top_results[0]

                # Run entity extraction via LLM (DSPy) for this single service
                start_time = time.time()
                await self._process_intent_detection(
                    services=[matched],
                    request=request,
                    chat_id=chat_id,
                    context=context,
                    costs_metric=costs_metric,
                )
                time_metric["service.intent_detection"] = time.time() - start_time

                # Ensure service_data is populated from hybrid match
                # _process_intent_detection may not set it if DSPy returns
                # a different service_id format, so we populate it explicitly
                if not context.get("service_data"):
                    context["service_id"] = matched.get("service_id")
                    context["service_data"] = matched
                    logger.info(
                        f"[{chat_id}] Populated service_data from hybrid match: "
                        f"{matched.get('name')}"
                    )

        elif needs_llm_confirmation is True:
            # AMBIGUOUS PATH: Multiple services scored similarly
            # Run LLM intent detection only on candidate services (not all services)
            top_results = context.get("top_results", [])
            logger.info(
                f"[{chat_id}] AMBIGUOUS SERVICE MATCH (non-streaming): "
                f"running LLM intent detection on {len(top_results)} candidates"
            )

            start_time = time.time()
            if top_results:
                await self._process_intent_detection(
                    services=top_results,
                    request=request,
                    chat_id=chat_id,
                    context=context,
                    costs_metric=costs_metric,
                )
            time_metric["service.discovery"] = time.time() - start_time

        else:
            # LEGACY PATH: No hybrid search metadata (classifier disabled or error)
            # Full service discovery + intent detection (original behavior)
            start_time = time.time()
            await self._log_request_details(
                request, context, mode="non-streaming", costs_metric=costs_metric
            )
            time_metric["service.discovery"] = time.time() - start_time

        # Check if service was detected and validated
        if not context.get("service_id"):
            logger.info(
                f"[{chat_id}] No service detected or validated - "
                f"returning None to fallback to next layer"
            )
            return None

        # Entity Transformation & Validation
        logger.info(f"[{chat_id}] Entity Transformation:")

        # Step 1: Extract service metadata from context
        start_time = time.time()
        service_metadata = self._extract_service_metadata(context, chat_id)
        if not service_metadata:
            logger.error(
                f"[{chat_id}]   - Metadata extraction failed - "
                f"returning None to fallback"
            )
            return None

        logger.info(f"[{chat_id}]   - Service: {service_metadata['service_name']}")
        logger.info(
            f"[{chat_id}]   - Schema entities: {service_metadata['entity_schema']}"
        )
        logger.info(
            f"[{chat_id}]   - Extracted entities: {service_metadata['entities_dict']}"
        )

        # Step 2: Validate entities against schema
        validation_result = self._validate_entities(
            extracted_entities=service_metadata["entities_dict"],
            service_schema=service_metadata["entity_schema"],
            service_name=service_metadata["service_name"],
            chat_id=chat_id,
        )
        time_metric["service.entity_validation"] = time.time() - start_time

        logger.info(
            f"[{chat_id}]   - Validation status: "
            f"{'PASSED ✓' if validation_result['is_valid'] else 'FAILED ✗'}"
        )

        if validation_result["missing_entities"]:
            logger.warning(
                f"[{chat_id}]   - Missing entities (will send empty strings): "
                f"{validation_result['missing_entities']}"
            )

        if validation_result["extra_entities"]:
            logger.info(
                f"[{chat_id}]   - Extra entities (ignored): "
                f"{validation_result['extra_entities']}"
            )

        if validation_result["validation_errors"]:
            for error in validation_result["validation_errors"]:
                logger.warning(f"[{chat_id}]   - Validation warning: {error}")

        # Step 3: Transform entities dict to ordered array
        entities_array = self._transform_entities_to_array(
            entities_dict=service_metadata["entities_dict"],
            entity_order=service_metadata["entity_schema"],
        )

        context["entities_array"] = entities_array
        context["validation_result"] = validation_result

        # Construct service endpoint URL
        endpoint_url = self._construct_service_endpoint(
            service_name=service_metadata["service_name"], chat_id=chat_id
        )

        context["endpoint_url"] = endpoint_url
        context["http_method"] = service_metadata["ruuter_type"]

        logger.info(f"[{chat_id}] Service prepared: {endpoint_url}")

        # TODO: STEP 7 - Call Ruuter service endpoint and return response
        # 1. Build payload: {"input": entities_array, "authorId": request.authorId, "chatId": request.chatId}
        # 2. Call endpoint using http_method (POST/GET) with SERVICE_CALL_TIMEOUT
        # 3. Parse Ruuter response and extract result
        # 4. Return OrchestrationResponse with actual service result
        # 5. Handle errors (timeout, HTTP errors, malformed JSON)

        # STEP 6: Return debug response (temporary until Step 7 - Ruuter call implemented)
        # REMOVE THIS BLOCK AFTER STEP 7 IMPLEMENTATION (START)
        debug_content = self._format_debug_response(
            service_name=service_metadata["service_name"],
            endpoint_url=endpoint_url,
            http_method=service_metadata["ruuter_type"],
            entities_array=entities_array,
        )

        logger.info(f"[{chat_id}] Returning debug response (Step 7 pending)")

        # Log costs after service workflow completes (follows RAG workflow pattern)
        if self.orchestration_service:
            self.orchestration_service.log_costs(costs_metric)

        return OrchestrationResponse(
            chatId=request.chatId,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=debug_content,
        )
        # REMOVE THIS BLOCK AFTER STEP 7 IMPLEMENTATION (END)

    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
        time_metric: Optional[Dict[str, float]] = None,
    ) -> Optional[AsyncIterator[str]]:
        """Execute service workflow in streaming mode.

        Uses classification metadata from hybrid search (same as execute_async).

        Args:
            request: Orchestration request
            context: Workflow context
            time_metric: Optional timing dictionary for unified tracking
        """

        chat_id = request.chatId

        # Create costs tracking dictionary (follows RAG workflow pattern)
        costs_metric: Dict[str, Dict[str, Any]] = {}
        # Use parent time_metric or create new one
        if time_metric is None:
            time_metric = {}

        # Check if classifier provided hybrid search metadata
        needs_llm_confirmation = context.get("needs_llm_confirmation")

        if needs_llm_confirmation is False:
            # HIGH CONFIDENCE PATH: Skip discovery, use matched service
            matched_service_name = context.get("matched_service_name")
            rrf_score = context.get("rrf_score", 0)

            logger.info(
                f"[{chat_id}] HIGH-CONFIDENCE SERVICE MATCH (streaming): "
                f"{matched_service_name} (rrf_score={rrf_score:.6f})"
            )

            top_results = context.get("top_results", [])
            if top_results:
                matched = top_results[0]

                start_time = time.time()
                await self._process_intent_detection(
                    services=[matched],
                    request=request,
                    chat_id=chat_id,
                    context=context,
                    costs_metric=costs_metric,
                )
                time_metric["service.intent_detection"] = time.time() - start_time

                # Ensure service_data is populated from hybrid match
                if not context.get("service_data"):
                    context["service_id"] = matched.get("service_id")
                    context["service_data"] = matched
                    logger.info(
                        f"[{chat_id}] Populated service_data from hybrid match: "
                        f"{matched.get('name')}"
                    )

        elif needs_llm_confirmation is True:
            # AMBIGUOUS PATH: Run LLM intent detection on candidates
            top_results = context.get("top_results", [])
            logger.info(
                f"[{chat_id}] AMBIGUOUS SERVICE MATCH (streaming): "
                f"{len(top_results)} candidates"
            )

            start_time = time.time()
            if top_results:
                await self._process_intent_detection(
                    services=top_results,
                    request=request,
                    chat_id=chat_id,
                    context=context,
                    costs_metric=costs_metric,
                )
            time_metric["service.discovery"] = time.time() - start_time

        else:
            # LEGACY PATH: Full service discovery (original behavior)
            start_time = time.time()
            await self._log_request_details(
                request, context, mode="streaming", costs_metric=costs_metric
            )
            time_metric["service.discovery"] = time.time() - start_time

        # Check if service was detected and validated
        if not context.get("service_id"):
            logger.info(
                f"[{chat_id}] No service detected or validated - "
                f"returning None to fallback to next layer"
            )
            return None

        # Entity Transformation & Validation
        logger.info(f"[{chat_id}] Entity Transformation:")

        # Step 1: Extract service metadata from context
        service_metadata = self._extract_service_metadata(context, chat_id)
        if not service_metadata:
            logger.error(
                f"[{chat_id}]   - Metadata extraction failed - "
                f"returning None to fallback"
            )
            return None

        logger.info(f"[{chat_id}]   - Service: {service_metadata['service_name']}")
        logger.info(
            f"[{chat_id}]   - Schema entities: {service_metadata['entity_schema']}"
        )
        logger.info(
            f"[{chat_id}]   - Extracted entities: {service_metadata['entities_dict']}"
        )

        # Step 2: Validate entities against schema
        validation_result = self._validate_entities(
            extracted_entities=service_metadata["entities_dict"],
            service_schema=service_metadata["entity_schema"],
            service_name=service_metadata["service_name"],
            chat_id=chat_id,
        )

        logger.info(
            f"[{chat_id}]   - Validation status: "
            f"{'PASSED ✓' if validation_result['is_valid'] else 'FAILED ✗'}"
        )

        if validation_result["missing_entities"]:
            logger.warning(
                f"[{chat_id}]   - Missing entities (will send empty strings): "
                f"{validation_result['missing_entities']}"
            )

        if validation_result["extra_entities"]:
            logger.info(
                f"[{chat_id}]   - Extra entities (ignored): "
                f"{validation_result['extra_entities']}"
            )

        if validation_result["validation_errors"]:
            for error in validation_result["validation_errors"]:
                logger.warning(f"[{chat_id}]   - Validation warning: {error}")

        # Step 3: Transform entities dict to ordered array
        entities_array = self._transform_entities_to_array(
            entities_dict=service_metadata["entities_dict"],
            entity_order=service_metadata["entity_schema"],
        )

        context["entities_array"] = entities_array
        context["validation_result"] = validation_result

        # Construct service endpoint URL
        endpoint_url = self._construct_service_endpoint(
            service_name=service_metadata["service_name"], chat_id=chat_id
        )

        context["endpoint_url"] = endpoint_url
        context["http_method"] = service_metadata["ruuter_type"]

        logger.info(f"[{chat_id}] Service prepared: {endpoint_url}")

        # TODO: STEP 7 - Call Ruuter service endpoint and stream response
        # 1. Build payload: {"input": entities_array, "authorId": request.authorId, "chatId": request.chatId}
        # 2. Call endpoint using http_method (POST/GET) with SERVICE_CALL_TIMEOUT
        # 3. Parse Ruuter response and extract result
        # 4. Format result as SSE and yield chunks
        # 5. Handle errors (timeout, HTTP errors, malformed JSON)

        # STEP 6: Return debug response as async iterator (temporary until Step 7)
        # REMOVE THIS BLOCK AFTER STEP 7 IMPLEMENTATION (START)
        debug_content = self._format_debug_response(
            service_name=service_metadata["service_name"],
            endpoint_url=endpoint_url,
            http_method=service_metadata["ruuter_type"],
            entities_array=entities_array,
        )

        logger.info(f"[{chat_id}] Streaming debug response (Step 7 pending)")

        if self.orchestration_service is None:
            raise RuntimeError("Orchestration service not initialized for streaming")

        # Store reference for closure (helps type checker)
        orchestration_service = self.orchestration_service

        async def debug_stream() -> AsyncIterator[str]:
            yield orchestration_service.format_sse(chat_id, debug_content)
            yield orchestration_service.format_sse(chat_id, "END")

            # Log costs after streaming completes (follows RAG workflow pattern)
            # Must be inside generator because costs are accumulated during streaming
            orchestration_service.log_costs(costs_metric)

        return debug_stream()
        # REMOVE THIS BLOCK AFTER STEP 7 IMPLEMENTATION (END)
