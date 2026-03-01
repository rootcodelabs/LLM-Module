# Tool Classifier Extension - System Specification

**Version**: 1.0  
**Date**: February 13, 2026  
**Status**: Design Specification  

---

## 1. Overview

This document specifies the extension of the existing RAG Module with a **Tool Classifier** that implements layer-wise workflow routing. The classifier determines whether a user query should be handled by:

1. **Service Workflow** - External service/API calls
2. **Context Workflow** - Conversation history-based responses  
3. **RAG Workflow** - Knowledge base retrieval (existing)
4. **OOD Response** - Out of domain fallback

### 1.1 Current State

**Existing Flow:**
```
User Query → Input Guardrails → Prompt Refiner → Contextual Retrieval → Response Generator → Output Guardrails
```

**Entry Points:**
- `POST /orchestrate` - Non-streaming orchestration
- `POST /orchestrate/test` - Testing environment with simplified input
- `POST /orchestrate/stream` - Server-sent events streaming

### 1.2 Proposed Extension

**New Flow:**
```
User Query → Input Guardrails → Tool Classifier → [Service | Context | RAG | OOD]
                                      ↓
                              Layer 1: Service Check
                                      ↓ (no match)
                              Layer 2: Context Check
                                      ↓ (no match)
                              Layer 3: RAG Retrieval
                                      ↓ (no chunks)
                              Layer 4: OOD Response
```

---

## 2. Architecture Changes

### 2.1 Component Integration

The Tool Classifier will be integrated into the existing `LLMOrchestrationService` with minimal disruption:

```python
# Location: src/llm_orchestration_service.py

def process_orchestration_request(self, request: OrchestrationRequest):
    """
    Modified orchestration pipeline with tool classifier.
    
    Pipeline:
    1. Language Detection (existing)
    2. Query Validation (existing) 
    3. Input Guardrails (existing, relocated)
    4. Tool Classifier (NEW)
    5. Workflow Routing (NEW)
    """
    
    # Existing: Step 0, 0.5
    detected_language = detect_language(request.message)
    validation_result = validate_query_basic(request.message)
    
    # Existing: Component initialization
    components = self._initialize_service_components(request)
    
    # Existing: Step 1 - Input Guardrails (RELOCATED before classifier)
    if components["guardrails_adapter"]:
        input_blocked = self.handle_input_guardrails(...)
        if input_blocked:
            return input_blocked
    
    # NEW: Step 2 - Tool Classifier
    classifier_result = self.tool_classifier.classify(
        query=request.message,
        conversation_history=request.conversationHistory,
        language=detected_language
    )
    
    # NEW: Step 3 - Workflow Routing
    if classifier_result.workflow == WorkflowType.SERVICE:
        return self._execute_service_workflow(request, classifier_result)
    elif classifier_result.workflow == WorkflowType.CONTEXT:
        return self._execute_context_workflow(request, classifier_result)
    elif classifier_result.workflow == WorkflowType.RAG:
        return self._execute_rag_workflow(request, classifier_result)
    else:
        return self._create_out_of_scope_response(request, detected_language)
```

### 2.2 New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `ToolClassifier` | `src/tool_classifier/classifier.py` | Main classifier logic |
| `ServiceWorkflowExecutor` | `src/tool_classifier/service_workflow.py` | Service discovery and triggering |
| `ContextWorkflowExecutor` | `src/tool_classifier/context_workflow.py` | LLM-based conversation history analysis |
| `IntentEntityExtractor` | `src/tool_classifier/intent_extractor.py` | LLM-based intent/entity detection |
| `ServiceDiscoveryManager` | `src/tool_classifier/service_discovery.py` | Qdrant semantic search for services |
| `IntentCollectionSync` | `src/tool_classifier/intent_sync_service.py` | Database → Qdrant synchronization |
| `ContextAnalyzer` | `src/tool_classifier/context_analyzer.py` | LLM-based context availability checker |

### 2.3 LLM Config Module Integration

The existing LLM Config Module (`src/llm_config_module/`) is reused by the tool classifier for all LLM-based operations. No modifications to the core module are required.

**Current LLM Config Module Capabilities:**
- **Multi-Provider Support**: Azure OpenAI, AWS Bedrock, OpenAI, Anthropic
- **Vault Integration**: Secure credential management via HashiCorp Vault
- **Connection Management**: Dynamic LLM connection selection based on `connection_id` from requests
- **Usage Tracking**: Token counting and cost calculation across providers

**Tool Classifier LLM Usage:**

| Workflow | LLM Operation | Config Usage | Temperature |
|----------|---------------|--------------|-------------|
| **Service (Layer 1)** | Intent & entity extraction | `llm_manager.call_llm_async()` | 0.0 (deterministic) |
| **Context (Layer 2)** | Context availability check | `llm_manager.call_llm_async()` | 0.0 (deterministic) |
| **RAG (Layer 3)** | Response generation | Existing integration | 0.7 (default) |
| **OOD (Layer 4)** | No LLM call | N/A | N/A |

**Integration Pattern:**

```python
# Tool classifier workflows use the same LLMManager instance
class ToolClassifier:
    def __init__(self, llm_manager: LLMManager, ...):
        self.llm_manager = llm_manager  # Reuse existing instance
    
    async def detect_intent(self, query: str, services: List[Service]):
        """Use LLM Config Module for intent detection."""
        response = await self.llm_manager.call_llm_async(
            prompt=INTENT_DETECTION_PROMPT.format(...),
            temperature=0.0,  # Deterministic for classification
            max_tokens=200
        )
        return parse_intent(response)
```

**Configuration Reuse:**
-  Same connection selection logic (`connection_id` from `OrchestrationRequest`)
-  Same Vault credential retrieval
-  Same cost tracking pattern (`get_lm_usage_since()`)
-  Same error handling and retry logic
-  Same provider-specific implementations

**No Changes Required**: The LLM Config Module is provider-agnostic and supports all tool classifier LLM calls out of the box.

---

## 3. Layer 1: Service Workflow

### 3.1 Workflow Logic

When a user query is received, the system determines if it's a service-related request through the following steps:

```
1. Service Count Check → 2. Service Discovery → 3. Intent Detection → 4. Service Validation → 5. Entity Transformation → 6. Service Triggering
```

### 3.2 Step-by-Step Implementation

#### Step 1: Service Count Check

**Purpose**: Optimize performance based on service catalog size

```python
# Query: SELECT COUNT(*) FROM services WHERE current_state = 'active' AND deleted = FALSE

if service_count <= 50:
    # Use all services for LLM context
    services = get_all_active_services()
else:
    # Use semantic search for top 20 most relevant
    services = semantic_search_services(user_query, top_k=20)
```

**Database Query:**
```sql
SELECT COUNT(*) FROM public.services 
WHERE current_state = 'active' AND deleted = FALSE;
```

#### Step 2: Semantic Search (When Service Count > 50)

**Tool**: Qdrant vector database  
**Collection**: `intent_collection`  
**Vector Dimension**: 3072 (text-embedding-3-large)

**Search Configuration:**
```python
search_params = {
    "collection_name": "intent_collection",
    "query_vector": embed_query(user_query),
    "limit": 20,
    "score_threshold": 0.5,  # Higher threshold for service matching
}
```

**Output Format:**
```json
[
  {
    "service_id": "exchange-rate-001",
    "service_name": "ExchangeRateService",
    "description": "Provides currency exchange rates",
    "entities": ["fromCurrency", "toCurrency"],
    "score": 0.87
  },
  ...
]
```

#### Step 3: LLM Intent Detection

**Action**: Call LLM with user query and service context to extract:
- `intent`: Service name to trigger
- `entities`: Key-value pairs of extracted parameters

**Prompt Template:**
```python
INTENT_DETECTION_PROMPT = """
You are an intent classifier for government services. Analyze the user query and determine which service should handle the request.

Available Services:
{service_list}

User Query: "{user_query}"

Task:
1. If the query matches a service, extract:
   - intent: The exact service name to trigger
   - entities: Key-value pairs of required parameters

2. If NO service matches, respond with: {{"intent": null, "entities": null}}

Response Format (JSON only, no explanation):
{{"intent": "ServiceName", "entities": {{"param1": "value1", "param2": "value2"}}}}
"""
```

**Expected LLM Response:**
```json
{
  "choices": [
    {
      "message": {
        "content": "{\"intent\": \"ExchangeRateService\", \"entities\": {\"fromCurrency\": \"EUR\", \"toCurrency\": \"USD\"}}"
      }
    }
  ]
}
```

**Parsing Logic:**
```python
# Parse LLM response
content = response["choices"][0]["message"]["content"]
parsed = json.loads(content)

if parsed["intent"] is None:
    # No service match - move to Layer 2 (Context Workflow)
    return WorkflowType.CONTEXT
```

#### Step 4: Service Validation

**Action**: Validate the detected service against the database

**Validation Query:**
```sql
SELECT service_id, name, ruuter_type, endpoints, structure, entities
FROM public.services
WHERE service_id = %(detected_service_id)s
  AND current_state = 'active'
  AND deleted = FALSE;
```

**Validation Checks:**
-  Service exists in database
-  `current_state = 'active'`
-  `deleted = FALSE`

**Failure Handling:**
```python
if not service_exists or not service_active:
    logger.warning(f"Service validation failed: {detected_service_id}")
    # Fallback to Layer 2 (Context Workflow)
    return WorkflowType.CONTEXT
```

#### Step 5: Entity Transformation

**Purpose**: Convert LLM entity object to array format for service payload

**Input (from LLM):**
```json
{
  "fromCurrency": "EUR",
  "toCurrency": "USD"
}
```

**Output (for service call):**
```json
["EUR", "USD"]
```

**Transformation Logic:**
```python
def transform_entities(entities: Optional[Dict[str, str]], 
                       entity_order: List[str]) -> List[str]:
    """
    Transform entity dictionary to ordered array.
    
    Args:
        entities: LLM-extracted entity key-value pairs
        entity_order: Expected entity order from service schema
    
    Returns:
        Ordered list of entity values
    """
    if not entities or entities is None:
        return []
    
    # Maintain order defined in service schema
    return [entities.get(key, "") for key in entity_order]
```

**Example:**
```python
# Service schema defines: entities = ["fromCurrency", "toCurrency"]
transform_entities(
    {"fromCurrency": "EUR", "toCurrency": "USD"}, 
    ["fromCurrency", "toCurrency"]
) 
# Output: ["EUR", "USD"]
```

#### Step 6: Service Triggering

**Purpose**: Call the external service endpoint with formatted payload

**URL Construction:**
```python
# From database field 'endpoints'
base_url = "http://ruuter:8086"  # From environment or service config
service_endpoint = f"{base_url}/services/active{service_name}"

# Example: http://ruuter:8086/services/activeExchangeRateService
```

**HTTP Method:**
```python
# Retrieved from database field 'ruuter_type'
method = service.ruuter_type  # 'GET' or 'POST' (ENUM)
```

**Payload Format:**
```json
{
  "input": ["EUR", "USD"],
  "authorId": "user-67890",
  "chatId": "chat-12345"
}
```

**Implementation:**
```python
async def trigger_service(
    service: ServiceRecord,
    entities: List[str],
    request: OrchestrationRequest
) -> Dict[str, Any]:
    """
    Trigger external service via Ruuter.
    
    Args:
        service: Validated service record from database
        entities: Transformed entity array
        request: Original orchestration request
    
    Returns:
        Service response or error
    """
    url = f"{RUUTER_BASE_URL}/services/active{service.name}"
    payload = {
        "input": entities,
        "authorId": request.authorId,
        "chatId": request.chatId
    }
    
    try:
        if service.ruuter_type == "GET":
            response = await http_client.get(url, params=payload, timeout=10)
        else:  # POST
            response = await http_client.post(url, json=payload, timeout=10)
        
        response.raise_for_status()
        return response.json()
    
    except httpx.TimeoutException:
        logger.error(f"Service timeout: {service.service_id}")
        raise ServiceTimeoutError()
    except httpx.HTTPStatusError as e:
        logger.error(f"Service error: {e.response.status_code}")
        raise ServiceExecutionError()
```

**Response Handling:**

**Non-Streaming:**
```python
service_response = await trigger_service(service, entities, request)
formatted_content = format_service_response(service_response)

# Apply output guardrails
if guardrails_adapter:
    output_check = await guardrails_adapter.check_output_async(formatted_content)
    costs_metric["output_guardrails"] = output_check.usage
    
    if not output_check.allowed:
        logger.warning(f"Service response blocked by guardrails: {output_check.reason}")
        return create_guardrail_violation_response(request)

# Return validated service response
return OrchestrationResponse(
    chatId=request.chatId,
    llmServiceActive=True,
    questionOutOfLLMScope=False,
    inputGuardFailed=False,
    content=formatted_content
)
```

**Streaming:**
```python
service_response = await trigger_service(service, entities, request)
formatted_content = format_service_response(service_response)

# Apply output guardrails validation
if guardrails_adapter:
    output_check = await guardrails_adapter.check_output_async(formatted_content)
    costs_metric["output_guardrails"] = output_check.usage
    
    if not output_check.allowed:
        logger.warning(f"Service response blocked by guardrails")
        yield format_sse(request.chatId, OUTPUT_GUARDRAIL_VIOLATION_MESSAGE)
        yield format_sse(request.chatId, "END")
        return

# Stream validated response token-by-token
for token in split_into_tokens(formatted_content, chunk_size=5):
    yield format_sse(request.chatId, token)
    await asyncio.sleep(0.01)  # Maintain streaming UX

yield format_sse(request.chatId, "END")
```

### 3.3 Failure Scenarios

| Scenario | Action |
|----------|--------|
| No intent detected | Move to Layer 2 (Context Workflow) |
| Service validation failed | Move to Layer 2 (Context Workflow) |
| Service call timeout | Return `SERVICE_TIMEOUT_ERROR` message |
| Service returns error | Return `SERVICE_EXECUTION_ERROR` message |
| Entity extraction incomplete | Attempt service call with partial entities, or fallback to Layer 2 |
| Output guardrails blocked | Return `OUTPUT_GUARDRAIL_VIOLATION_MESSAGE` or fallback to Layer 2 |

### 3.4 Output Guardrails for Service Responses

**Why Service Responses Need Guardrails:**
- External services may return PII (personal identifiable information)
- Service errors could expose sensitive system details
- Third-party API responses are untrusted content
- Ensures consistent safety across all workflows

**Integration Pattern:**

Both non-streaming and streaming modes validate service responses before sending to users:

```python
# Get service response
service_response = await trigger_service(...)

# Apply output guardrails (validation-first)
if guardrails_adapter:
    output_check = await guardrails_adapter.check_output_async(service_response)
    if not output_check.allowed:
        # Blocked - return error or fallback
        return create_guardrail_violation_response(request)

# Validated - return/stream to user
return/stream service_response
```

---

## 4. Layer 2: Context Workflow

### 4.1 Workflow Logic

If Layer 1 fails (no service match), use LLM to determine if the query is a greeting or can be answered from conversation history.

**Trigger Conditions:**
-  No service intent detected in Layer 1
-  Query is a greeting (hello, hi, good morning, etc.) **OR**
-  Conversation history exists (at least 1 previous turn) and query references it

### 4.2 Greeting Detection

Greetings and conversational pleasantries are handled by the Context Workflow to provide natural, friendly responses without triggering service discovery or RAG retrieval.

**Greeting Patterns (Multilingual):**

```python
# Estonian greetings
ESTONIAN_GREETINGS = [
    "tere", "tervist", "tere hommikust", "tere päevast", "tere õhtust",
    "hei", "hommikust", "õhtust", "päevast", "nägemist",
    "tsau", "moi", "moikka"
]

# English greetings
ENGLISH_GREETINGS = [
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "greetings", "howdy", "morning", "afternoon", "evening"
]

# Farewell patterns
FAREWELL_PATTERNS = [
    "goodbye", "bye", "see you", "talk to you later", "ttyl",
    "nägemist", "head aega", "kuni", "tsau"
]
```

**LLM-Based Greeting Detection:**

Instead of rigid pattern matching, the LLM analyzes whether the query is a greeting or conversational message:

```python
async def detect_greeting(
    query: str,
    llm_manager: LLMManager,
    language: str
) -> GreetingResult:
    """
    Use LLM to detect if query is a greeting/conversational message.
    
    Args:
        query: User's message
        llm_manager: LLM manager instance
        language: Detected language (et/en)
    
    Returns:
        GreetingResult with is_greeting flag and optional response
    """
    prompt = GREETING_DETECTION_PROMPT.format(
        user_query=query,
        language=language
    )
    
    response = await llm_manager.call_llm_async(
        prompt=prompt,
        temperature=0.0,
        max_tokens=150
    )
    
    content = response["choices"][0]["message"]["content"]
    result = json.loads(content)
    
    return GreetingResult(
        is_greeting=result["is_greeting"],
        greeting_type=result.get("greeting_type"),  # 'hello', 'goodbye', 'thanks', etc.
        suggested_response=result.get("suggested_response")
    )
```

**Greeting Detection Prompt:**

```python
GREETING_DETECTION_PROMPT = """
You are a greeting classifier. Determine if the user's message is a greeting, farewell, or conversational pleasantry.

User Message: "{user_query}"
Language: {language}

Task:
1. Identify if this is a greeting/conversational message (hello, hi, goodbye, thanks, etc.)
2. If YES: Classify the type and suggest an appropriate response
3. If NO: Indicate it's not a greeting

Response Format (JSON only):
{{
  "is_greeting": true/false,
  "greeting_type": "hello" | "goodbye" | "thanks" | "casual" | null,
  "suggested_response": "friendly response in same language" | null
}}

Examples of greetings:
- "Tere!" → {"is_greeting": true, "greeting_type": "hello"}
- "Good morning" → {"is_greeting": true, "greeting_type": "hello"}
- "Thanks for your help" → {"is_greeting": true, "greeting_type": "thanks"}
- "What are digital signatures?" → {"is_greeting": false}
"""
```

**Response Generation:**

```python
if greeting_result.is_greeting:
    # Use LLM-suggested response or fallback to predefined messages
    response = greeting_result.suggested_response or get_default_greeting_response(
        greeting_type=greeting_result.greeting_type,
        language=language
    )
    
    return OrchestrationResponse(
        chatId=request.chatId,
        llmServiceActive=True,
        questionOutOfLLMScope=False,
        inputGuardFailed=False,
        content=response
    )
```

### 4.3 LLM-Based Context Analysis

Instead of using regex patterns, we use the LLM to intelligently determine if the query references conversation history and can be answered from it.

**Conversation Window:**
```python
# Consider last 10 conversation turns (5 user + 5 bot pairs)
CONTEXT_WINDOW_SIZE = 10

def get_recent_history(history: List[ConversationItem]) -> List[ConversationItem]:
    """Get recent conversation history for context analysis."""
    return history[-CONTEXT_WINDOW_SIZE:] if history else []
```

**LLM Context Check Prompt:**
```python
CONTEXT_CHECK_PROMPT = """
You are a conversation context analyzer. Analyze if the user's current query can be answered using ONLY the conversation history provided.

Conversation History:
{conversation_history}

Current User Query: "{user_query}"

Task:
1. First check if this is a greeting/conversational message (hi, hello, thanks, goodbye, etc.)
2. If it's a greeting: Provide an appropriate friendly response
3. If NOT a greeting: Determine if the query references or can be answered from the conversation history above
4. If YES: Extract and provide the answer from the conversation history
5. If NO: Indicate that it cannot be answered from conversation history

Response Format (JSON only, no explanation):
{{
  "is_greeting": true/false,
  "can_answer_from_context": true/false,
  "answer": "extracted answer from history OR greeting response" OR null,
  "reasoning": "brief explanation of why it can/cannot be answered"
}}

Examples of GREETINGS (handle with friendly response):
- "Tere!" → {"is_greeting": true, "answer": "Tere! Kuidas saan teid aidata?"}
- "Hello" → {"is_greeting": true, "answer": "Hello! How can I help you?"}
- "Thanks!" → {"is_greeting": true, "answer": "You're welcome!"}
- "Good morning" → {"is_greeting": true, "answer": "Good morning! What can I do for you?"}

Examples of queries that CAN be answered from context:
- "What did you say earlier about that?"
- "Can you repeat that?"
- "What was the rate you mentioned?"
- "Tell me more about what you just said"

Examples of queries that CANNOT be answered from context:
- Completely new topics
- Requests for real-time data
- Questions requiring external knowledge
"""
```

**Implementation:**
```python
async def check_context_availability(
    query: str,
    conversation_history: List[ConversationItem],
    llm_manager: LLMManager
) -> ContextCheckResult:
    """
    Use LLM to check if query can be answered from conversation history.
    
    Args:
        query: Current user query
        conversation_history: Recent conversation turns
        llm_manager: LLM manager for making calls
    
    Returns:
        ContextCheckResult with can_answer flag and optional answer
    """
    # Get recent history
    recent_history = get_recent_history(conversation_history)
    
    if not recent_history:
        # No conversation history available
        return ContextCheckResult(
            can_answer_from_context=False,
            answer=None,
            reasoning="No conversation history available"
        )
    
    # Format conversation history for prompt
    history_text = format_conversation_history(recent_history)
    
    # Call LLM with structured output request
    prompt = CONTEXT_CHECK_PROMPT.format(
        conversation_history=history_text,
        user_query=query
    )
    
    try:
        response = await llm_manager.call_llm_async(
            prompt=prompt,
            temperature=0.0,  # Deterministic for classification
            max_tokens=300
        )
        
        # Parse structured JSON response
        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        return ContextCheckResult(
            is_greeting=result.get("is_greeting", False),
            can_answer_from_context=result["can_answer_from_context"],
            answer=result.get("answer"),
            reasoning=result.get("reasoning", "")
        )
    
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse LLM context check response: {e}")
        # Fallback: assume cannot answer from context
        return ContextCheckResult(
            can_answer_from_context=False,
            answer=None,
            reasoning="Failed to parse LLM response"
        )

def format_conversation_history(history: List[ConversationItem]) -> str:
    """Format conversation history for LLM prompt."""
    formatted = []
    for i, item in enumerate(history, 1):
        role = "User" if item.authorRole == "user" else "Assistant"
        formatted.append(f"{i}. {role}: {item.message}")
    return "\n".join(formatted)
```

**Response Models:**
```python
from pydantic import BaseModel

class ContextCheckResult(BaseModel):
    """Result from LLM context availability check."""
    is_greeting: bool = False
    can_answer_from_context: bool
    answer: Optional[str] = None
    reasoning: str = ""

class GreetingResult(BaseModel):
    """Result from greeting detection."""
    is_greeting: bool
    greeting_type: Optional[str] = None  # 'hello', 'goodbye', 'thanks', 'casual'
    suggested_response: Optional[str] = None
```

### 4.3 Workflow Execution

**Non-Streaming Response:**
```python
async def execute_context_workflow(
    request: OrchestrationRequest,
    llm_manager: LLMManager,
    guardrails_adapter: Optional[NeMoRailsAdapter],
    costs_metric: Dict
) -> Optional[OrchestrationResponse]:
    """
    Execute context-based response workflow with output guardrails.
    
    Returns:
        OrchestrationResponse with context-based answer or None to fallback to next layer
    """
    # Check if query can be answered from conversation history
    context_result = await check_context_availability(
        query=request.message,
        conversation_history=request.conversationHistory,
        llm_manager=llm_manager
    )
    
    # Track costs
    costs_metric["context_check"] = get_lm_usage_since(history_before)
    
    if (context_result.is_greeting or context_result.can_answer_from_context) and context_result.answer:
        logger.info(
            f"[{request.chatId}] Query answered from context "
            f"(greeting: {context_result.is_greeting})"
        )
        
        # Apply output guardrails validation
        if guardrails_adapter:
            output_check = await guardrails_adapter.check_output_async(
                context_result.answer
            )
            costs_metric["output_guardrails"] = output_check.usage
            
            if not output_check.allowed:
                logger.warning(
                    f"[{request.chatId}] Context response blocked by guardrails: "
                    f"{output_check.reason}"
                )
                return create_guardrail_violation_response(request)
        
        # Return validated context-based response
        return OrchestrationResponse(
            chatId=request.chatId,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=context_result.answer
        )
    
    else:
        logger.info(
            f"[{request.chatId}] Cannot answer from context: {context_result.reasoning}"
        )
        # Fallback to Layer 3 (RAG Workflow)
        return None  # Signal to move to next layer
```

**Streaming Response:**
```python
async def execute_context_workflow_streaming(
    request: OrchestrationRequest,
    llm_manager: LLMManager,
    guardrails_adapter: Optional[NeMoRailsAdapter],
    costs_metric: Dict
) -> Optional[AsyncIterator[str]]:
    """
    Execute context workflow with streaming support and output guardrails.
    
    Yields:
        SSE-formatted strings with validated context-based response
    
    Returns:
        None if cannot answer from context (signals fallback to next layer)
    """
    # Check context availability (non-streaming, fast)
    context_result = await check_context_availability(
        query=request.message,
        conversation_history=request.conversationHistory,
        llm_manager=llm_manager
    )
    
    # Track costs
    costs_metric["context_check"] = get_lm_usage_since(history_before)
    
    if (context_result.is_greeting or context_result.can_answer_from_context) and context_result.answer:
        logger.info(
            f"[{request.chatId}] Validating and streaming context-based response "
            f"(greeting: {context_result.is_greeting})"
        )
        
        # Apply output guardrails validation BEFORE streaming
        if guardrails_adapter:
            output_check = await guardrails_adapter.check_output_async(
                context_result.answer
            )
            costs_metric["output_guardrails"] = output_check.usage
            
            if not output_check.allowed:
                logger.warning(
                    f"[{request.chatId}] Context response blocked by guardrails (streaming)"
                )
                yield format_sse(request.chatId, OUTPUT_GUARDRAIL_VIOLATION_MESSAGE)
                yield format_sse(request.chatId, "END")
                return
        
        # Response validated - stream token by token for consistent UX
        for token in split_into_tokens(context_result.answer, chunk_size=5):
            yield format_sse(request.chatId, token)
            await asyncio.sleep(0.01)  # Maintain streaming pace
        
        # Signal completion
        yield format_sse(request.chatId, "END")
    
    else:
        logger.info(f"[{request.chatId}] No context match, falling back to RAG")
        # Return None to signal fallback to next layer
        # Caller will handle RAG workflow
        return None

def split_into_tokens(text: str, chunk_size: int = 5) -> List[str]:
    """Split text into token-like chunks for streaming simulation."""
    words = text.split()
    tokens = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        tokens.append(chunk + " " if i + chunk_size < len(words) else chunk)
    return tokens
```

### 4.4 Advantages of LLM-Based Approach

 **No Regex Pattern Maintenance**: LLM understands semantic context references naturally  
 **Handles Edge Cases**: Can detect implicit references that regex would miss  
 **Multilingual Support**: Works across Estonian, English, and other languages  
 **Structured Output**: Consistent JSON format for easy parsing  
 **Reasoning Transparency**: Includes explanation of decision  
 **Streaming Compatible**: Fast context check + token-by-token answer delivery  
 **Greeting Detection**: Automatically handles greetings, farewells, and conversational pleasantries  
 **Natural Responses**: LLM generates contextually appropriate greeting responses

### 4.7 Fallback Strategy

**Fallback to Layer 3 (RAG):**
- If `is_greeting = false` AND `can_answer_from_context = false`
- If LLM response parsing fails
- If conversation history is empty (and not a greeting)
- If output guardrails block the response (fallback to RAG for alternative answer)

**Error Handling:**
```python
try:
    result = await execute_context_workflow(
        request, llm_manager, guardrails_adapter, costs_metric
    )
    if result:
        return result  # Context-based answer (validated)
    else:
        # Move to Layer 3 (RAG)
        return await execute_rag_workflow(request, components, costs_metric)
except Exception as e:
    logger.error(f"Context workflow failed: {e}")
    # Fallback to RAG workflow
    return await execute_rag_workflow(request, components, costs_metric)
```

**Guardrail Violation Fallback:**
```python
# Option 1: Return error message (current approach)
if not output_check.allowed:
    return create_guardrail_violation_response(request)

# Option 2: Fallback to RAG (alternative approach)
if not output_check.allowed:
    logger.warning("Context response blocked, trying RAG workflow")
    return await execute_rag_workflow(request, components, costs_metric)
```

---

## 5. Layer 3: RAG Workflow

### 5.1 Integration with Existing System

**Trigger**: When both Layer 1 (Service) and Layer 2 (Context) fail to match

**Implementation:**
```python
# Reuse existing RAG pipeline
return self._execute_orchestration_pipeline(
    request, components, costs_metric, time_metric
)
```

**Existing Flow (No Changes Required):**
1. Prompt Refinement
2. Contextual Retrieval (Qdrant + BM25)
3. Rank Fusion (RRF)
4. Response Generation
5. Output Guardrails (validation-first streaming already implemented)

**Streaming with Output Guardrails (Current Implementation):**
```python
# RAG workflow uses validation-first approach
async for validated_chunk in guardrails_adapter.stream_with_guardrails(
    user_message=refined_query,
    bot_message_generator=llm_streaming_generator
):
    # NeMo buffers tokens (chunk_size=200)
    # Validates each buffer before yielding
    yield format_sse(chatId, validated_chunk)

yield format_sse(chatId, "END")
```

**Fallback:**
- If no chunks found (`len(relevant_chunks) == 0`) → Layer 4 (OOD)
- If response confidence low → Layer 4 (OOD)

---

## 5.2 Streaming + Output Guardrails Comparison

### Summary: How Each Workflow Handles Streaming + Validation

| Workflow | Response Source | Validation Approach | Streaming Method |
|----------|----------------|---------------------|------------------|
| **RAG** | LLM streaming generation | NeMo buffers + validates chunks (chunk_size=200) | `stream_with_guardrails()` wraps bot generator |
| **Service** | External service (complete) | Validate complete response | Stream validated response token-by-token |
| **Context** | LLM structured output (complete) | Validate complete response | Stream validated response token-by-token |
| **OOD** | Fixed message | No validation needed | Stream fixed message token-by-token |

### Technical Flow for Each Workflow

#### RAG Workflow (Existing - Validation-First)

**Non-Streaming:**
```python
response = await response_generator.generate(...)
output_check = await guardrails_adapter.check_output_async(response)
if output_check.allowed:
    return OrchestrationResponse(content=response)
```

**Streaming:**
```python
# LLM generates via streaming
async def bot_generator():
    async for token in llm.stream():
        yield token

# NeMo validates in real-time (buffers chunks)
async for validated_chunk in guardrails_adapter.stream_with_guardrails(
    user_message=query,
    bot_message_generator=bot_generator
):
    yield format_sse(chatId, validated_chunk)  # Already validated
```

#### Service Workflow (New - Validate Then Stream)

**Non-Streaming:**
```python
service_response = await call_external_service(...)  # Complete response
output_check = await guardrails_adapter.check_output_async(service_response)
if output_check.allowed:
    return OrchestrationResponse(content=service_response)
else:
    return GuardrailViolationResponse()
```

**Streaming:**
```python
service_response = await call_external_service(...)  # Complete response

# Validate complete response FIRST
output_check = await guardrails_adapter.check_output_async(service_response)
if not output_check.allowed:
    yield format_sse(chatId, OUTPUT_GUARDRAIL_VIOLATION_MESSAGE)
    yield format_sse(chatId, "END")
    return

# Validated - now stream to client token-by-token
for token in split_into_tokens(service_response, chunk_size=5):
    yield format_sse(chatId, token)
    await asyncio.sleep(0.01)
yield format_sse(chatId, "END")
```

#### Context Workflow (New - Validate Then Stream)

**Non-Streaming:**
```python
context_result = await llm.check_context(query, history)  # Complete answer
if context_result.can_answer_from_context:
    output_check = await guardrails_adapter.check_output_async(context_result.answer)
    if output_check.allowed:
        return OrchestrationResponse(content=context_result.answer)
    else:
        return GuardrailViolationResponse()
```

**Streaming:**
```python
context_result = await llm.check_context(query, history)  # Complete answer

if context_result.can_answer_from_context:
    # Validate complete answer FIRST
    output_check = await guardrails_adapter.check_output_async(context_result.answer)
    if not output_check.allowed:
        yield format_sse(chatId, OUTPUT_GUARDRAIL_VIOLATION_MESSAGE)
        yield format_sse(chatId, "END")
        return
    
    # Validated - stream to client token-by-token
    for token in split_into_tokens(context_result.answer, chunk_size=5):
        yield format_sse(chatId, token)
        await asyncio.sleep(0.01)
    yield format_sse(chatId, "END")
```

### Key Differences

**RAG Workflow:**
-  **Real-time validation**: LLM generates → NeMo validates chunks → Stream to client
-  **Buffered approach**: Tokens buffered in chunks of 200 characters
-  **Bi-directional**: Generator feeding into NeMo, NeMo yielding validated chunks
-  **Cost**: Inline (no separate validation call)

**Service/Context Workflows:**
-  **Pre-validation**: Get complete response → Validate → Stream to client
-  **Complete response**: Already have full text before streaming starts
-  **Uni-directional**: Simply chunk and send validated response
-  **Cost**: Separate validation call tracked in `costs_metric["output_guardrails"]`
-  **UX Consistency**: Simulates streaming to match RAG workflow behavior

### Why Different Approaches?

1. **RAG**: LLM streaming is inherently token-by-token, so NeMo can validate in real-time
2. **Service**: External API returns complete response, no streaming generation occurs
3. **Context**: LLM returns structured JSON with complete answer, not streaming

### Common Pattern: Validation-First

All three workflows share the **validation-first principle**:
-  Content is validated BEFORE reaching the user
-  Blocked content never sent to client
-  Consistent safety guarantees across all workflows
-  Streaming provides smooth UX even with complete responses (Service/Context)

---

## 6. Layer 4: OOD (Out of Domain) Response

### 6.1 Trigger Conditions

-  No service detected (Layer 1 failed)
-  No context match (Layer 2 failed)
-  No relevant knowledge chunks (Layer 3 failed)

### 6.2 Response Generation

**Return localized OOD message:**
```python
return OrchestrationResponse(
    chatId=request.chatId,
    llmServiceActive=True,
    questionOutOfLLMScope=True,  # Flag as out of scope
    inputGuardFailed=False,
    content=get_localized_message(OUT_OF_SCOPE_MESSAGES, detected_language)
)
```

**Existing Constants (Reuse):**
```python
# From: src/llm_orchestrator_config/llm_ochestrator_constants.py
OUT_OF_SCOPE_MESSAGES = {
    "et": "Vabandust, ma ei suuda sellele küsimusele vastata...",
    "en": "I apologize, but I cannot answer this question..."
}
```

---

## 7. Data Schemas

### 7.1 Database Schema

**Table: `services`**

```sql
-- Location: DSL/Liquibase/changelog/rag-search-script-v6-services.sql

-- Custom ENUM types
CREATE TYPE ruuter_request_type AS ENUM ('GET', 'POST');
CREATE TYPE service_state AS ENUM ('active', 'inactive', 'draft');

CREATE TABLE public.services (
  -- Primary key
  id BIGINT PRIMARY KEY,
  
  -- Basic service information
  name TEXT NOT NULL,                          -- Service name (e.g., "ExchangeRateService")
  description TEXT NOT NULL,                   -- Human-readable description
  service_id TEXT NOT NULL UNIQUE,             -- Unique identifier (e.g., "exchange-rate-001")
  
  -- Service classification
  ruuter_type ruuter_request_type DEFAULT 'GET',  -- HTTP method: 'GET' or 'POST'
  current_state service_state DEFAULT 'draft',    -- State: 'active', 'inactive', 'draft'
  is_common BOOLEAN NOT NULL DEFAULT FALSE,       -- Is this a common/shared service?
  deleted BOOLEAN NOT NULL DEFAULT FALSE,         -- Soft delete flag
  
  -- Intent classification data (for LLM)
  slot TEXT NOT NULL DEFAULT '',                  -- Reserved for future use
  entities text[] NOT NULL DEFAULT '{}',          -- Expected entity names ["entity1", "entity2"]
  examples text[] NOT NULL DEFAULT '{}',          -- Example queries
  
  -- Service configuration
  structure JSON NOT NULL DEFAULT '{}',           -- Service schema/structure
  endpoints JSON NOT NULL DEFAULT '[]',           -- Endpoint configurations
  
  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE UNIQUE INDEX idx_services_service_id ON public.services(service_id);
CREATE INDEX idx_services_active ON public.services(current_state, deleted) 
  WHERE deleted = FALSE;
CREATE INDEX idx_services_name ON public.services(name);
```

**Update Master Changelog:**
```yaml
# Location: DSL/Liquibase/master.yml

databaseChangeLog:
  - include:
      file: changelog/rag-search-script-v1-llm-connections.sql
  - include:
      file: changelog/rag-search-script-v2-user-management.sql
  - include:
      file: changelog/rag-search-script-v3-configuration.sql
  - include:
      file: changelog/rag-search-script-v4-authority-data.xml
  - include:
      file: changelog/rag-search-script-v5-prompt-config.sql
  - include:
      file: changelog/rag-search-script-v6-services.sql  # NEW
```

### 7.2 Qdrant Collection Schema

**Collection Name:** `intent_collection`

**Configuration:**
```python
{
  "collection_name": "intent_collection",
  "vectors_config": {
    "size": 3072,  # text-embedding-3-large
    "distance": "Cosine"
  }
}
```

**Document Schema:**
```json
{
  "id": "common_service_companies_workforce_taxes",
  "name": "Ettevõtte tööjõumaksud",
  "description": "Kasutaja soovib infot ettevõtte poolt tasutud tööjõumaksude kohta, näiteks palgamaksud ja sotsiaalmaks.",
  "examples": [
    "ettevõtte tasutud tööjõumaksud",
    "kui palju maksis ettevõte tööjõumakse",
    "firma poolt tasutud tööjõumaksud"
  ],
  "entities": ["company_name"],
  "text_for_embedding": "Kasutaja soovib infot ettevõtte poolt tasutud tööjõumaksude kohta, näiteks palgamaksud ja sotsiaalmaks.\nettevõtte tasutud tööjõumaksud\nkui palju maksis ettevõte tööjõumakse\nfirma poolt tasutud tööjõumaksud",
  
  "service_id": "common_service_companies_workforce_taxes",  
  "ruuter_type": "POST",
  "current_state": "active"
}
```

**Field Mapping:**
| Qdrant Field | Source | Purpose |
|--------------|--------|---------|
| `id` | `services.service_id` | Unique identifier |
| `name` | `services.name` | Service display name |
| `description` | `services.description` | Service description |
| `examples` | `services.examples` | Example queries |
| `entities` | `services.entities` | Expected parameters |
| `text_for_embedding` | Computed | Concatenated text for vector embedding |
| `service_id` | `services.service_id` | Link to database record |
| `ruuter_type` | `services.ruuter_type` | HTTP method |
| `current_state` | `services.current_state` | Service status |

**Embedding Text Construction:**
```python
def construct_embedding_text(service: ServiceRecord) -> str:
    """
    Construct text for embedding from service data.
    Format: description + examples (newline-separated)
    """
    parts = [service.description]
    parts.extend(service.examples)
    return "\n".join(parts)
```

### 7.3 Database → Qdrant Synchronization

**Trigger Mechanism:**
```sql
-- PostgreSQL NOTIFY/LISTEN pattern or polling
CREATE OR REPLACE FUNCTION notify_service_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        PERFORM pg_notify(
            'service_sync', 
            json_build_object(
                'action', TG_OP,
                'service_id', NEW.service_id,
                'current_state', NEW.current_state
            )::text
        );
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM pg_notify(
            'service_sync', 
            json_build_object(
                'action', 'DELETE',
                'service_id', OLD.service_id
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER service_sync_trigger
AFTER INSERT OR UPDATE OR DELETE ON services
FOR EACH ROW EXECUTE FUNCTION notify_service_change();
```

**Sync Service:**
```python
# Location: src/tool_classifier/intent_sync_service.py

class IntentCollectionSyncService:
    """Synchronizes services table with Qdrant intent_collection."""
    
    async def handle_service_change(self, event: Dict):
        action = event['action']
        service_id = event['service_id']
        
        if action in ['INSERT', 'UPDATE']:
            # Fetch service from database
            service = await self.db.fetch_service(service_id)
            
            # Generate embedding
            embedding_text = self.construct_embedding_text(service)
            embedding_vector = await self.embed(embedding_text)
            
            # Upsert to Qdrant
            await self.qdrant_client.upsert(
                collection_name="intent_collection",
                points=[{
                    "id": service.service_id,
                    "vector": embedding_vector,
                    "payload": {
                        "name": service.name,
                        "description": service.description,
                        "examples": service.examples,
                        "entities": service.entities,
                        "text_for_embedding": embedding_text,
                        "service_id": service.service_id,
                        "ruuter_type": service.ruuter_type,
                        "current_state": service.current_state
                    }
                }]
            )
        
        elif action == 'DELETE':
            await self.qdrant_client.delete(
                collection_name="intent_collection",
                points_selector={"points": [service_id]}
            )
```

---

## 8. Error Messages & Constants

### 8.1 New Error Messages

**Location:** `src/llm_orchestrator_config/llm_ochestrator_constants.py`

```python
# Service Workflow Errors
SERVICE_NOT_FOUND_MESSAGES = {
    "et": "Vabandust, ma ei leidnud sobivat teenust teie päringu jaoks.",
    "en": "Sorry, I couldn't find a matching service for your request.",
}

SERVICE_VALIDATION_FAILED_MESSAGES = {
    "et": "Teenus ei ole hetkel saadaval.",
    "en": "The requested service is currently unavailable.",
}

SERVICE_TIMEOUT_ERROR_MESSAGES = {
    "et": "Teenuse vastus võttis liiga kaua aega. Palun proovige hiljem uuesti.",
    "en": "The service took too long to respond. Please try again later.",
}

SERVICE_EXECUTION_ERROR_MESSAGES = {
    "et": "Teenuse kutsumine ebaõnnestus. Palun proovige hiljem uuesti.",
    "en": "Service execution failed. Please try again later.",
}

ENTITY_EXTRACTION_FAILED_MESSAGES = {
    "et": "Ma ei suutnud teie päringust vajalikku infot tuvastada.",
    "en": "I couldn't extract the required information from your query.",
}

# Context Workflow Errors
INSUFFICIENT_CONTEXT_MESSAGES = {
    "et": "Ma ei leia vastust meie eelmisest vestlusest. Kas saate täpsustada?",
    "en": "I can't find the answer in our previous conversation. Can you clarify?",
}

NO_CONTEXT_AVAILABLE_MESSAGES = {
    "et": "Mul pole piisavalt konteksti teie küsimusele vastamiseks.",
    "en": "I don't have enough context to answer your question.",
}

# Greeting Responses
GREETING_HELLO_MESSAGES = {
    "et": "Tere! Kuidas saan teid aidata?",
    "en": "Hello! How can I help you?",
}

GREETING_GOODBYE_MESSAGES = {
    "et": "Head aega! Kui vajate abi, olen siin.",
    "en": "Goodbye! If you need help, I'm here.",
}

GREETING_THANKS_MESSAGES = {
    "et": "Pole tänu väärt! Kas saan veel kuidagi aidata?",
    "en": "You're welcome! Can I help you with anything else?",
}

GREETING_CASUAL_MESSAGES = {
    "et": "Tere! Mida te soovite teada?",
    "en": "Hi there! What would you like to know?",
}
```

**Helper Function for Default Greeting Responses:**

```python
def get_default_greeting_response(greeting_type: str, language: str) -> str:
    """
    Get default greeting response based on type and language.
    
    Args:
        greeting_type: Type of greeting ('hello', 'goodbye', 'thanks', 'casual')
        language: Language code ('et', 'en')
    
    Returns:
        Localized greeting response
    """
    greeting_map = {
        "hello": GREETING_HELLO_MESSAGES,
        "goodbye": GREETING_GOODBYE_MESSAGES,
        "thanks": GREETING_THANKS_MESSAGES,
        "casual": GREETING_CASUAL_MESSAGES
    }
    
    messages = greeting_map.get(greeting_type, GREETING_HELLO_MESSAGES)
    return messages.get(language, messages["en"])
```

### 8.2 Reused Constants

```python
# Already defined - reuse for consistency
OUT_OF_SCOPE_MESSAGE
TECHNICAL_ISSUE_MESSAGE
INPUT_GUARDRAIL_VIOLATION_MESSAGE
OUTPUT_GUARDRAIL_VIOLATION_MESSAGE
```

---

## 9. API Integration

### 9.1 Entry Points (No Changes)

The tool classifier is transparent to API consumers. All existing endpoints continue to work:

**Non-Streaming:**
```http
POST /orchestrate
Content-Type: application/json

{
  "chatId": "session-123",
  "message": "What is the EUR to USD exchange rate?",
  "authorId": "user-456",
  "conversationHistory": [],
  "url": "https://example.com",
  "environment": "production",
  "connection_id": "conn-789"
}
```

**Streaming:**
```http
POST /orchestrate/stream
Content-Type: application/json

(Same request body as /orchestrate)
```

**Testing:**
```http
POST /orchestrate/test
Content-Type: application/json

{
  "message": "Convert 100 EUR to USD",
  "environment": "testing",
  "connectionId": 1
}
```

### 9.2 Response Format (No Changes)

**Success Response:**
```json
{
  "chatId": "session-123",
  "llmServiceActive": true,
  "questionOutOfLLMScope": false,
  "inputGuardFailed": false,
  "content": "The current EUR to USD exchange rate is 1.08."
}
```

**Service Workflow Response:**
```json
{
  "chatId": "session-123",
  "llmServiceActive": true,
  "questionOutOfLLMScope": false,
  "inputGuardFailed": false,
  "content": "Based on the ExchangeRateService: EUR/USD = 1.0850"
}
```

The response format remains unchanged. The workflow selection is internal and transparent to the API consumer.

---

## 10. Implementation Considerations

### 10.1 Performance Optimization

**Service Discovery Caching:**
```python
# Cache active service count for 5 minutes
@cached(ttl=300)
async def get_active_service_count() -> int:
    return await db.count_active_services()
```

**Intent Collection Warm-up:**
```python
# Pre-load intent collection on startup
async def warmup_intent_collection():
    """Ensure intent_collection is ready before processing requests."""
    collection_info = await qdrant_client.get_collection("intent_collection")
    logger.info(f"Intent collection ready: {collection_info.points_count} services")
```

### 10.2 Monitoring & Analytics

**Tool Classifier Decisions Table:**
```sql
-- Track classifier decisions for analytics
CREATE TABLE tool_classifier_decisions (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    author_id TEXT,
    user_query TEXT NOT NULL,
    detected_workflow VARCHAR(20) NOT NULL,  -- 'service', 'context', 'rag', 'ood'
    classifier_confidence NUMERIC(5,4),
    service_id VARCHAR(100),  -- If service workflow
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_classifier_decisions_workflow 
  ON tool_classifier_decisions(detected_workflow);
```

### 10.3 Cost Tracking

**Add tracking for new LLM calls:**
# Service workflow - intent detection
costs_metric["intent_detection"] = {
    "total_prompt_tokens": usage.prompt_tokens,
    "total_completion_tokens": usage.completion_tokens,
    "total_cost": calculate_cost(usage)
}

# Context workflow - context availability check
costs_metric["context_check
costs_metric["intent_detection"] = {
    "total_prompt_tokens": usage.prompt_tokens,
    "total_completion_tokens": usage.completion_tokens,
    "total_cost": calculate_cost(usage)
}
```

### 10.4 Guardrails Strategy

**Output Guardrails Application:**
```python
# Apply output guardrails to ALL workflows for consistency
WORKFLOWS_WITH_OUTPUT_GUARDRAILS = [
    WorkflowType.SERVICE,   # Check service responses (may contain PII/sensitive data)
    WorkflowType.CONTEXT,   # Check context-based responses (conversation history may have PII)
    WorkflowType.RAG        # Existing behavior (knowledge base responses)
]

# OOD responses skip guardrails (fixed message)
WORKFLOWS_WITHOUT_OUTPUT_GUARDRAILS = [
    WorkflowType.OOD
]
```

**Validation-First Approach:**

All workflows use the **validation-first** approach where content is validated BEFORE streaming to the client:

1. **RAG Workflow** (existing):
   - LLM generates response via streaming
   - NeMo buffers tokens (chunk_size=200)
   - Each buffer validated before yielding
   - Uses `stream_with_guardrails()` method

2. **Service Workflow** (new):
   - External service returns complete response
   - Apply output guardrails validation
   - Stream validated response token-by-token to client
   - Consistent UX with RAG workflow

3. **Context Workflow** (new):
   - LLM returns complete answer from history
   - Apply output guardrails validation
   - Stream validated response token-by-token to client
   - Consistent UX with RAG workflow

**Streaming + Output Guardrails Integration:**

```python
# For Service and Context workflows
async def stream_validated_response(
    response_text: str,
    guardrails_adapter: NeMoRailsAdapter,
    request: OrchestrationRequest,
    costs_metric: Dict
) -> AsyncIterator[str]:
    """
    Apply output guardrails and stream validated response.
    
    Flow:
    1. Validate complete response with guardrails
    2. If allowed: Stream token-by-token to client
    3. If blocked: Send guardrail violation message
    """
    # Check output guardrails (non-streaming validation)
    output_check = await guardrails_adapter.check_output_async(response_text)
    
    # Track costs
    costs_metric["output_guardrails"] = output_check.usage
    
    if not output_check.allowed:
        logger.warning(f"[{request.chatId}] Output blocked by guardrails")
        # Send violation message
        yield format_sse(request.chatId, OUTPUT_GUARDRAIL_VIOLATION_MESSAGE)
        yield format_sse(request.chatId, "END")
        return
    
    # Response validated - stream to client
    logger.info(f"[{request.chatId}] Streaming validated response")
    for token in split_into_tokens(response_text):
        yield format_sse(request.chatId, token)
        await asyncio.sleep(0.01)  # Maintain streaming pace
    
    yield format_sse(request.chatId, "END")
```

**Utility Function for Token Streaming:**
```python
def split_into_tokens(text: str, chunk_size: int = 5) -> List[str]:
    """
    Split text into token-like chunks for streaming simulation.
    
    Used by Service and Context workflows to provide streaming UX
    even though the complete response is already available.
    
    Args:
        text: Complete response text
        chunk_size: Number of words per chunk
    
    Returns:
        List of text chunks
    """
    words = text.split()
    tokens = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        tokens.append(chunk + " " if i + chunk_size < len(words) else chunk)
    return tokens
```

### 10.5 Streaming Implementation Summary

| Aspect | RAG Workflow | Service Workflow | Context Workflow |
|--------|--------------|------------------|------------------|
| **Response Type** | Streaming (token-by-token) | Complete (all at once) | Complete (all at once) |
| **Validation Timing** | Real-time (buffered chunks) | Pre-validation | Pre-validation |
| **Guardrail Method** | `stream_with_guardrails()` | `check_output_async()` | `check_output_async()` |
| **Streaming Reason** | Natural (LLM streams) | UX consistency | UX consistency |
| **Token Buffering** | NeMo 200-char chunks | Manual 5-word chunks | Manual 5-word chunks |
| **Cost Tracking** | Inline (timing = 0.0) | Separate call | Separate call |
| **Blocked Handling** | Stop mid-stream | Pre-check, don't stream | Pre-check, don't stream |
| **Client Experience** | Progressive reveal | Progressive reveal | Progressive reveal |

**Implementation Status:**
-  RAG streaming + guardrails: **Already implemented** (production-ready)
-  Service streaming + guardrails: **To be implemented** (spec complete)
-  Context streaming + guardrails: **To be implemented** (spec complete)

---

## 11. Testing Strategy

### 11.1 Unit Tests
async def test_context_detection_with_llm():
    query = "What did you say earlier?"
    history = [
        ConversationItem(authorRole="bot", message="The EUR to USD rate is 1.08"),
        ConversationItem(authorRole="user", message="Thanks")
    ]
    result = await context_analyzer.check_context_availability(query, history)
    assert result.can_answer_from_context == True
    assert "1.08" in result.answer

async def test_context_detection_no_reference():
    query = "What are digital signatures?"
    history = [ConversationItem(message="The rate is 1.08", ...)]
    result = await context_analyzer.check_context_availability(query, history)
    assert result.can_answer_from_context == False

def test_rag_fallback():
    query = "What are digital signatures?"
    result = classifier.classify(query, [])
    assert result.workflow == WorkflowType.RAG

async def test_context_streaming():
    """Test that context workflow supports streaming."""
    query = "What was the rate?"
    history = [ConversationItem(message="The rate is 1.08", ...)]
    
    tokens = []
    async for token in context_workflow.execute_streaming(query, history):
        tokens.append(token)
    
    assert len(tokens) > 0
    assert tokens[-1] == "END"
    query = "What did you say earlier?"
    history = [ConversationItem(message="The rate is 1.08", ...)]
    result = classifier.classify(query, history)
    assert result.workflow == WorkflowType.CONTEXT

def test_rag_fallback():
    query = "What are digital signatures?"
    result = classifier.classify(query, [])
    assert result.workflow == WorkflowType.RAG
```

### 11.2 Integration Tests

```python
# tests/integration_tests/test_service_workflow.py
async def test_full_service_workflow():
    request = OrchestrationRequest(
        message="Convert 100 EUR to USD",
        chatId="test-123",
        ...
    )
    response = await orchestration_service.process_orchestration_request(request)
    assert response.llmServiceActive == True
    assert "exchange rate" in response.content.lower()
```

### 11.3 Load `ContextAnalyzer` with LLM-based context checking
-  Create context check prompt template with structured output
-  Implement `ContextWorkflowExecutor` with streaming support
-  Add conversation history formatting utilities
-  Integration tests for context workflow (streaming + non-streaming)
-  Cost tracking for context check LLM calls>50 services
locust -f tests/load/test_classifier_load.py --users 100 --spawn-rate 10
```

---

## 12. Migration Path

### 12.1 Phase 1:
-  Create database migration for `services` table
-  Create Qdrant `intent_collection`
-  Relocate input guardrails before tool classifier
-  Define error message constants

### 12.2 Phase 2:
-  Implement `ToolClassifier` with rule-based logic
-  Implement workflow routing in `LLMOrchestrationService`
-  Add classifier decision logging
-  Unit tests for classifier

### 12.3 Phase 3: Service Workflow
-  Implement `ServiceDiscoveryManager` (Qdrant semantic search)
-  Implement `IntentEntityExtractor` (LLM-based)
-  Implement `ServiceWorkflowExecutor` (validation & triggering)
-  Implement `IntentCollectionSyncService` (DB → Qdrant)
-  Integration tests for service workflow

### 12.4 Phase 4: Context Workflow
- ✅ ImpleHECK_TEMPERATURE=0.0  # Deterministic for classification
CONTEXT_CHECK_MAX_TOKENS=300tection
-  Implement conversation history semantic search
-  Implement `ContextWorkflowExecutor`
-  Integration tests for context workflow

### 12.5 Phase 5: Finalization
-  Extend output guardrails to service & context workflows
-  Implement fallback chain (service → context → rag → ood)
-  Add comprehensive error handling
-  Performance optimization (caching, async)
-  End-to-end testing
-  Production deployment

---

## 13. Configuration

### 13.1 Environment Variables

```bash
# Service Workflow Configuration
RUUTER_BASE_URL=http://ruuter:8086
SERVICE_DISCOVERY_TIMEOUT=2  # seconds
SERVICE_CALL_TIMEOUT=10  # seconds
MAX_SERVICES_FOR_LLM_CONTEXT=50

# Qdrant Configuration
QDRANT_INTENT_COLLECTION=intent_collection
INTENT_SEARCH_TOP_K=20
INTENT_SEARCH_THRESHOLD=0.5

# Context Workflow Configuration
CONTEXT_WINDOW_SIZE=10
CONTEXT_CONFIDENCE_THRESHOLD=0.7
```

### 13.2 Feature Flags

```python
# src/llm_orchestrator_config/feature_flags.py

class FeatureFlags:
    # Enable/disable tool classifier (rollback switch)
    TOOL_CLASSIFIER_ENABLED = os.getenv("TOOL_CLASSIFIER_ENABLED", "true").lower() == "true"
    
    # Enable/disable specific workflows
    SERVICE_WORKFLOW_ENABLED = os.getenv("SERVICE_WORKFLOW_ENABLED", "true").lower() == "true"
    CONTEXT_WORKFLOW_ENABLED = os.getenv("CONTEXT_WORKFLOW_ENABLED", "true").lower() == "true"
    
    # Fallback to RAG if tool classifier fails
    FALLBACK_TO_RAG_ON_ERROR = True
```

---

## 14. Rollback Strategy

### 14.1 Graceful Degradation

```python
def process_orchestration_request(self, request: OrchestrationRequest):
    """Process with tool classifier or fallback to RAG."""
    
    if not FeatureFlags.TOOL_CLASSIFIER_ENABLED:
        # Fallback: Use existing RAG-only pipeline
        logger.info("Tool classifier disabled - using RAG pipeline")
        return self._execute_rag_workflow(request, None)
    
    try:
        # New: Tool classifier routing
        classifier_result = self.tool_classifier.classify(...)
        return self._route_to_workflow(request, classifier_result)
    
    except Exception as e:
        logger.error(f"Tool classifier failed: {e}")
        if FeatureFlags.FALLBACK_TO_RAG_ON_ERROR:
            logger.info("Falling back to RAG workflow")
            return self._execute_rag_workflow(request, None)
        raise
```

## 15. Success Metrics

### 15.1 Performance Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Tool Classifier Latency | < 200ms | p95 response time |
| Service Discovery (>50 services) | < 500ms | Qdrant search + LLM intent |
| Service Call Success Rate | > 95% | Successful service executions |
| Context Match Accuracy | > 80% | Correct context-based responses |
| End-to-End Latency | < 3s | Request to response |

### 15.2 Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Workflow Classification Accuracy | > 90% | Manual evaluation sample |
| Service Intent Accuracy | > 85% | Correct service selection |
| Entity Extraction Accuracy | > 90% | Correct entity values |
| False Positive Rate (Service) | < 5% | Incorrect service routing |
| User Satisfaction | > 4.0/5.0 | User feedback surveys |

---
