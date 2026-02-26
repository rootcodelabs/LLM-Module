# Tool Classifier and Service Workflow Architecture

## Overview

The Tool Classifier implements a **layer-wise fallback architecture** that routes user queries to the most appropriate workflow handler. The Service Workflow (Layer 1) handles external API/service calls with intelligent intent detection and entity extraction.

---

## Tool Classifier - Layer Architecture

### Design Pattern: Chain of Responsibility

The classifier tries each layer sequentially. If a layer returns `None`, it falls back to the next layer:

```
Layer 1: SERVICE  → External API calls (currency, weather, etc.)
Layer 2: CONTEXT  → Greetings, conversation history queries
Layer 3: RAG      → Knowledge base retrieval (documents, regulations)
Layer 4: OOD      → Out-of-domain fallback (polite rejection)
```

### Layer Execution Flow

```python
# Non-streaming mode
classification = await classifier.classify(query, history, language)
response = await classifier.route_to_workflow(classification, request, is_streaming=False)

# Streaming mode
classification = await classifier.classify(query, history, language)
stream = await classifier.route_to_workflow(classification, request, is_streaming=True)
async for sse_chunk in stream:
    yield sse_chunk
```

### Fallback Chain

Each workflow's `execute_async()` or `execute_streaming()` can return:
- **OrchestrationResponse / AsyncIterator[str]**: Layer handled the query successfully
- **None**: Layer cannot handle → Fallback to next layer

Example cascading:
```
Query: "What is VAT rate?"
└─ SERVICE (Layer 1) → No matching service → Returns None
   └─ CONTEXT (Layer 2) → Not a greeting → Returns None
      └─ RAG (Layer 3) → Found in docs → Returns response ✓
```

---

## Service Workflow (Layer 1) - Detailed Architecture

### Purpose
Handle queries that require calling external services/APIs:
- Currency conversion: "How much is 100 EUR in USD?"
- Weather services: "What's the temperature in Tallinn?"
- Custom Ruuter endpoints: Any service registered in database

### High-Level Flow

```
1. Service Discovery
   ↓
2. Service Selection (Semantic Search or LLM-based)
   ↓
3. Intent Detection (DSPy LLM Call)
   ↓
4. Entity Extraction (From LLM Output)
   ↓
5. Entity Validation (Against Service Schema)
   ↓
6. Entity Transformation (Dict → Ordered Array)
   ↓
7. Service Call (TODO: Ruuter endpoint invocation)
```

---

## 1. Service Discovery

### Method: `_call_service_discovery()`

Calls Ruuter public endpoint to fetch available services:

```python
GET /rag-search/get-services-from-llm
```

**Response Structure:**
```json
{
  "response": {
    "service_count": 15,
    "use_semantic_search": true,
    "services": [
      {
        "serviceId": "currency_conversion_eur",
        "name": "Currency Conversion (EUR Base)",
        "description": "Convert EUR to other currencies",
        "ruuterType": "POST",
        "ruuterUrl": "/currency/convert",
        "entities": ["target_currency"],
        "examples": [
          "How much is 100 EUR in USD?",
          "Convert EUR to JPY"
        ]
      }
    ]
  }
}
```

### Service Count Threshold Logic

```python
SERVICE_COUNT_THRESHOLD = 10

if service_count <= 10:
    # Few services → Use all services for LLM intent detection
    services = response["services"]
    
elif service_count > 10:
    # Many services → Use semantic search to narrow down
    services = await _semantic_search_services(query, top_k=5)
```

---

## 2. Service Selection

### Semantic Search (When Many Services)

**Method:** `_semantic_search_services()`

Uses Qdrant vector database to find relevant services:

```python
# 1. Generate embedding for user query
embedding = orchestration_service.create_embeddings_for_indexer([query])

# 2. Search Qdrant collection
search_payload = {
    "vector": query_embedding,
    "limit": 5,                        # Top 5 services
    "score_threshold": 0.4,            # Minimum similarity
    "with_payload": True
}

response = qdrant_client.post(
    f"/collections/{QDRANT_COLLECTION}/points/search",
    json=search_payload
)
```

**Returns:** Top-K most semantically relevant services for intent detection

---

## 3. Intent Detection (LLM-Based)

### Method: `_detect_service_intent()`

Uses **DSPy + LLM** to intelligently match user query to a specific service and extract entities.

### DSPy Module: `IntentDetectionModule`

**Purpose:** Analyze user query against available services and extract structured information

**Signature:**
```python
class ServiceIntentDetector(dspy.Signature):
    # Inputs
    user_query: str                    # "How much is 100 EUR in USD?"
    available_services: str            # JSON of service definitions
    conversation_context: str          # Recent 3 conversation turns
    
    # Output
    intent_result: str                 # JSON: {matched_service_id, confidence, entities, reasoning}
```

### LLM Call Flow

```python
# 1. Prepare service context
services_formatted = [
    {
        "service_id": "currency_conversion_eur",
        "name": "Currency Conversion",
        "description": "Convert EUR to other currencies",
        "required_entities": ["target_currency"],
        "examples": ["How much is EUR in USD?", "Convert EUR to JPY"]
    }
]

# 2. Prepare conversation context (last 3 turns)
conversation_context = """
user: Hello
assistant: Hi! How can I help?
user: How much is 100 EUR in USD?
"""

# 3. Call DSPy module
intent_result = intent_detector.forward(
    user_query="How much is 100 EUR in USD?",
    services=services_formatted,
    conversation_history=conversation_history
)
```

### LLM Output Format

The LLM returns structured JSON:

```json
{
  "matched_service_id": "currency_conversion_eur",
  "confidence": 0.95,
  "entities": {
    "target_currency": "USD"
  },
  "reasoning": "User wants to convert EUR to USD, matches currency conversion service"
}
```

### Confidence Threshold

```python
if confidence < 0.7:
    # Low confidence → Service workflow returns None → Fallback to RAG
    return None
```

### Cost Tracking

Intent detection is an LLM call, so costs are tracked:

```python
# Before LLM call
history_length_before = len(dspy.settings.lm.history)

# Call intent detector
intent_result = intent_module.forward(...)

# After LLM call
usage_info = get_lm_usage_since(history_length_before)
costs_metric["intent_detection"] = usage_info

# Later: orchestration_service.log_costs(costs_metric)
```

---

## 4. Entity Extraction

### From LLM Output

The LLM extracts entities directly from the user query:

**User Query:** `"Palju saan 1 EUR eest THBdes?"`  
(Estonian: "How much do I get for 1 EUR in THB?")

**LLM Extraction:**
```json
{
  "entities": {
    "target_currency": "THB"
  }
}
```

### Entity Format

Entities are extracted as **key-value pairs** where:
- **Key**: Entity name defined in service schema (`target_currency`)
- **Value**: Extracted value from user query (`"THB"`)

### Multi-Entity Example

**Service Schema:**
```json
{
  "serviceId": "weather_forecast",
  "entities": ["location", "date"]
}
```

**User Query:** "What's the weather in Tallinn tomorrow?"

**LLM Extraction:**
```json
{
  "entities": {
    "location": "Tallinn",
    "date": "tomorrow"
  }
}
```

---

## 5. Entity Validation

### Method: `_validate_entities()`

Validates extracted entities against the service's expected schema.

### Validation Checks

#### 1. Missing Entities
Entities required by schema but not extracted by LLM:

```python
service_schema = ["target_currency", "amount"]
extracted = {"target_currency": "USD"}

# Missing: "amount"
missing_entities = ["amount"]
```

**Strategy:** Send empty string for missing entities (let service validate)

#### 2. Extra Entities
Entities extracted but not in service schema:

```python
service_schema = ["target_currency"]
extracted = {"target_currency": "USD", "random_field": "value"}

# Extra: "random_field"
extra_entities = ["random_field"]
```

**Strategy:** Ignore extra entities (not sent to service)

#### 3. Empty Values
Entities extracted but with empty values:

```python
extracted = {"target_currency": ""}

validation_errors = ["Entity 'target_currency' has empty value"]
```

**Strategy:** Log warning, proceed anyway (service validates)

### Validation Result

```python
{
  "is_valid": True,                    # Always true (lenient validation)
  "missing_entities": ["amount"],      # Will send empty strings
  "extra_entities": ["random_field"],  # Will be ignored
  "validation_errors": [               # Warnings only
    "Entity 'amount' has empty value"
  ]
}
```

### Validation Philosophy

**Lenient Approach:**
- Always returns `is_valid: True`
- Proceeds with partial entities
- Service endpoint validates required parameters
- Avoids false negatives from over-strict validation

---

## 6. Entity Transformation

### Method: `_transform_entities_to_array()`

Transforms entity dictionary to **ordered array** matching service schema order.

### Why Ordered Array?

Ruuter services expect parameters in specific order:
```python
# Service schema defines order
entities_schema = ["target_currency", "source_currency", "amount"]

# LLM extraction (unordered dict)
entities_dict = {
  "amount": "100",
  "target_currency": "USD",
  "source_currency": "EUR"
}

# Transform to ordered array
entities_array = ["USD", "EUR", "100"]
#                  ↑      ↑      ↑
#                  [0]    [1]    [2]  (matches schema order)
```

### Transformation Logic

```python
def _transform_entities_to_array(
    entities_dict: Dict[str, str],
    entity_order: List[str]
) -> List[str]:
    """Transform entity dict to ordered array."""
    ordered_array = []
    
    for entity_key in entity_order:
        # Get value from dict, or empty string if missing
        value = entities_dict.get(entity_key, "")
        ordered_array.append(value)
    
    return ordered_array
```

### Example

**Service Schema:**
```json
["target_currency", "base_currency", "amount"]
```

**Extracted Entities:**
```json
{
  "target_currency": "JPY",
  "amount": "500"
}
```

**Transformed Array:**
```python
["JPY", "", "500"]
#        ↑
#   Missing "base_currency" → empty string
```

---

## 7. Service Call (TODO: Step 7)

### Endpoint Construction

```python
endpoint_url = f"{RUUTER_BASE_URL}/services/active{service_name}"
# Example: "http://ruuter:8080/services/active/currency-conversion"
# (Note: service_name from service metadata, e.g., "/currency-conversion")
```

### Payload Construction (Planned)

```python
payload = {
    "input": entities_array,         # ["USD", "EUR", "100"]
    "authorId": request.authorId,
    "chatId": request.chatId
}
```

### HTTP Call (Planned)

```python
# Non-streaming
response = await httpx.post(
    endpoint_url,
    json=payload,
    timeout=5.0
)

# Streaming
async with httpx.stream("POST", endpoint_url, json=payload) as stream:
    async for line in stream.aiter_lines():
        yield orchestration_service.format_sse(chat_id, line)
```

---

## Complete Example Flow

### User Query
```
"Palju saan 1 EUR eest THBdes?"
(How much do I get for 1 EUR in THB?)
```

### Step-by-Step Execution

#### 1. Service Discovery
```json
{
  "service_count": 5,
  "services": [
    {
      "serviceId": "currency_conversion_eur",
      "name": "Currency Conversion (EUR)",
      "entities": ["target_currency"],
      "examples": ["How much is EUR in USD?"]
    }
  ]
}
```

#### 2. Service Selection
```python
# Few services (5 <= 10) → Use all for intent detection
services = discovery_result["services"]
```

#### 3. Intent Detection (LLM Call)
```json
{
  "matched_service_id": "currency_conversion_eur",
  "confidence": 0.92,
  "entities": {
    "target_currency": "THB"
  },
  "reasoning": "User wants to convert EUR to THB"
}
```

#### 4. Entity Extraction
```python
entities_dict = {"target_currency": "THB"}
```

#### 5. Entity Validation
```python
validation_result = {
  "is_valid": True,
  "missing_entities": [],
  "extra_entities": [],
  "validation_errors": []
}
```

#### 6. Entity Transformation
```python
# Schema: ["target_currency"]
# Dict: {"target_currency": "THB"}
# Array: ["THB"]
entities_array = ["THB"]
```

#### 7. Service Call (TODO)
```python
# Planned implementation
response = await call_service(
    url="http://ruuter:8080/currency/convert",
    method="POST",
    payload={"input": ["THB"], "chatId": "..."}
)
```

---

## Cost Tracking

Service workflow tracks LLM costs following the RAG workflow pattern:

```python
# Create costs dict at workflow level
costs_metric: Dict[str, Dict[str, Any]] = {}

# Intent detection captures costs
intent_result, intent_usage = await _detect_service_intent(...)
costs_metric["intent_detection"] = intent_usage

# Log costs after workflow completes
orchestration_service.log_costs(costs_metric)
```

**Cost Breakdown Logged:**
```
LLM USAGE COSTS BREAKDOWN:
  intent_detection    : $0.000120 (1 calls, 450 tokens)
```

---

## Fallback Behavior

### When Service Workflow Returns None

```python
# Scenario 1: No service match (confidence < 0.7)
if not intent_result or intent_result.get("confidence", 0) < 0.7:
    return None  # Fallback to CONTEXT layer

# Scenario 2: Service validation failed
if not validated_service:
    return None  # Fallback to CONTEXT layer

# Scenario 3: No services discovered
if not services:
    return None  # Fallback to CONTEXT layer
```

### Fallback Chain Result

```
Query: "What is VAT?"
└─ SERVICE → No service matches "VAT information" → None
   └─ CONTEXT → Not a greeting → None
      └─ RAG → Found in knowledge base → Response ✓
```

---

## Configuration Constants

```python
# Service discovery
RUUTER_BASE_URL = "http://ruuter.public:8080"
SERVICE_DISCOVERY_TIMEOUT = 5.0  # seconds

# Service selection thresholds
SERVICE_COUNT_THRESHOLD = 10      # Switch to semantic search if exceeded
MAX_SERVICES_FOR_LLM_CONTEXT = 20 # Max services to pass to LLM

# Semantic search
QDRANT_COLLECTION = "services_collection"
SEMANTIC_SEARCH_TOP_K = 5         # Top 5 relevant services
SEMANTIC_SEARCH_THRESHOLD = 0.4   # Minimum similarity score
QDRANT_TIMEOUT = 2.0              # seconds

# Intent detection
INTENT_CONFIDENCE_THRESHOLD = 0.7 # Minimum confidence to proceed
```

---

## Key Design Decisions

### 1. **Lenient Entity Validation**
- Proceeds with partial entities
- Service validates required parameters
- Reduces false negatives

### 2. **Ordered Entity Arrays**
- Ruuter services expect positional parameters
- Schema defines canonical order
- Missing entities → empty strings

### 3. **Two-Stage Service Selection**
- Few services (≤10): Pass all to LLM
- Many services (>10): Semantic search first

### 4. **LLM-Based Intent Detection**
- Intelligent service matching
- Natural language understanding
- Multilingual support (Estonian, English, Russian)

### 5. **Cost Tracking**
- Follows RAG workflow pattern
- Tracks intent detection LLM costs
- Integrated with budget system

---

## Summary

The Tool Classifier's layer architecture enables intelligent query routing with graceful fallbacks. The Service Workflow (Layer 1) uses **LLM-based intent detection** to match user queries to external services, extract entities, validate them against service schemas, and prepare them for service invocation—all while maintaining comprehensive cost tracking and seamless integration with the broader RAG pipeline.
