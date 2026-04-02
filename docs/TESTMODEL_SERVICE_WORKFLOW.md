# TestModel Page — Service Workflow Documentation

This document traces the **service workflow** end-to-end through the **TestModel** UI page. It covers two scenarios:

1. **Natural-language service detection** — the user types a free-text query that the system classifies as a service.
2. **MCQ button-click** — the user clicks a choice button whose payload is a `#service` command, short-circuiting the NLU pipeline.

---

## Architecture Overview

```
┌─────────────┐       POST /rag-search/inference/test        ┌─────────────────┐
│  TestModel   │ ──────────────────────────────────────────▷  │  Ruuter (proxy)  │
│  (GUI)       │                                              │  /rag-search/    │
│  index.tsx   │ ◁─────────── JSON response ────────────────  │  inference/test  │
└─────────────┘                                              └───────┬─────────┘
                                                                     │
                                                    POST /orchestrate/test
                                                                     ▼
                                                             ┌───────────────────────┐
                                                             │ llm_orchestration_     │
                                                             │ service_api.py         │
                                                             │ test_orchestrate_      │
                                                             │ llm_request()          │
                                                             └───────┬───────────────┘
                                                                     │
                                                 OrchestrationRequest (mapped with defaults)
                                                                     ▼
                                                             ┌───────────────────────┐
                                                             │ llm_orchestration_     │
                                                             │ service.py             │
                                                             │ process_orchestration_ │
                                                             │ request()              │
                                                             └───────────────────────┘
```

---

## Key Files

| Layer | File | Purpose |
|---|---|---|
| **GUI** | `GUI/src/pages/TestModel/index.tsx` | UI page with connection selector, text input, result display, MCQ buttons |
| **GUI Service** | `GUI/src/services/inference.ts` | `viewInferenceResult()` — POST to `/rag-search/inference/test` |
| **API Layer** | `src/llm_orchestration_service_api.py` | `/orchestrate/test` handler — maps `TestOrchestrationRequest` → `OrchestrationRequest` and calls `process_orchestration_request()` |
| **Orchestration** | `src/llm_orchestration_service.py` | `process_orchestration_request()` — the core pipeline (language detection → `#service` prefix check → query validation → guardrails → classifier → service workflow) |
| **Service Workflow** | `src/tool_classifier/workflows/service_workflow.py` | `ServiceWorkflowExecutor` — service discovery, intent detection, entity extraction, endpoint call, direct step execution |
| **Models** | `src/models/request_models.py` | `OrchestrationRequest`, `OrchestrationResponse`, `TestOrchestrationRequest`, `TestOrchestrationResponse`, `ChoiceButton` |
| **Constants** | `src/tool_classifier/constants.py` | `SERVICE_STEP_PREFIXES`, `RUUTER_SERVICE_BASE_URL`, search thresholds |

---

## Flow 1: Natural-Language Service Detection

### 1.1 Frontend — User Sends a Message

The user selects an LLM connection from the dropdown and types a query (e.g., *"My keyboard is not working"*).

**`TestModel/index.tsx` → `handleSend()`** (line 72):
```tsx
inferenceMutation.mutate({
  llmConnectionId: Number(testLLM.connectionId),
  message: testLLM.text,
});
```

**`inference.ts` → `viewInferenceResult()`** (line 50):
```ts
const { data } = await apiDev.post(inferenceEndpoints.VIEW_TEST_INFERENCE_RESULT(), {
  connectionId: request.llmConnectionId,
  message: request.message,
});
```

This POST goes to `/rag-search/inference/test` (via Ruuter proxy), which maps to the backend `/orchestrate/test` endpoint.

### 1.2 API Layer — Request Mapping

**`llm_orchestration_service_api.py` → `test_orchestrate_llm_request()`** (line 313):
- Receives a `TestOrchestrationRequest` (only `message`, `environment`, optional `connectionId`).
- Maps to a full `OrchestrationRequest` with defaults:

```python
full_request = OrchestrationRequest(
    chatId="test-session",
    message=request.message,
    authorId="test-user",
    conversationHistory=[],
    url="test-context",
    environment=request.environment,
    connection_id=str(request.connectionId) if request.connectionId is not None else None,
)
```

- Calls `orchestration_service.process_orchestration_request(full_request)`.

### 1.3 Orchestration Pipeline — Service Detection

**`llm_orchestration_service.py` → `process_orchestration_request()`** (line 279):

```
STEP 0:   Language detection → detect_language(request.message) → "en"

STEP 0.1: Check request.message.startswith(SERVICE_STEP_PREFIXES)
          → FALSE (natural language) → skip, continue normally

STEP 0.5: Query validation → validate_query_basic(request.message) → valid

STEP 1:   Component initialization → LLM manager, guardrails adapter

STEP 2:   Input guardrails check → allowed

STEP 3:   ToolClassifier.classify(query, conversation_history, language)
          → Classification(workflow=SERVICE, confidence=0.92)
              The classifier uses hybrid search (dense + BM25) against
              the intent_collections Qdrant collection.

STEP 4:   route_to_workflow(classification, request, is_streaming=False)
          → Routes to ServiceWorkflowExecutor.execute_async()
```

### 1.4 ServiceWorkflowExecutor — `execute_async()`

**`service_workflow.py` → `execute_async()`** (line 699):

The executor uses **classification metadata** from hybrid search to decide how to proceed. There are three paths:

| Condition | Path |
|---|---|
| `needs_llm_confirmation == False` | High-confidence match — run intent detection on the single top match only |
| `needs_llm_confirmation == True` | Ambiguous — run intent detection on top-N candidates |
| No metadata | Fall back to full discovery flow (`_log_request_details`) |

#### Service Discovery (full flow)

1. **`_call_service_discovery(chat_id)`** — calls `GET http://ruuter-public:8086/rag-search/services/get-services`
2. Checks if `service_count > SERVICE_COUNT_THRESHOLD (10)` → triggers **semantic search** via Qdrant
3. Otherwise uses the services list directly

#### Intent Detection

**`_process_intent_detection(services, request, chat_id, context, costs_metric)`**:
1. Calls **`_detect_service_intent()`** → uses `IntentDetectionModule` (DSPy LLM) with:
   - The user query
   - The candidate services list
   - Conversation history
2. Returns matched `service_id`, `confidence`, `entities`
3. **`_validate_detected_service()`** — confirms the matched service exists in the active services list

#### Entity Extraction & Validation

```python
service_metadata = self._extract_service_metadata(context, chat_id)
# → {service_id, service_name, entities_dict, entity_schema, ruuter_type, is_common}

validation_result = self._validate_entities(entities_dict, entity_schema, service_name, chat_id)
# → checks missing, extra, empty entities

entities_array = self._transform_entities_to_array(entities_dict, entity_schema)
# → ordered list of entity values matching service schema
```

#### Service Endpoint Call

```python
endpoint_url = self._construct_service_endpoint(service_name, chat_id, is_common)
# → "http://ruuter:8086/services/services/active/Klaviatuuri_probleemi_lahendamine"

service_result = await self._call_service_endpoint(
    endpoint_url, http_method, entities_array, chat_id, author_id
)
```

**`_call_service_endpoint()`** (line 523):
1. Sends POST/GET to the Ruuter endpoint with payload `{chatId, authorId, input: entities_array}`
2. Ruuter executes the DSL → DMapper produces the response
3. Parses the response:
   - Unwraps `{"response": ...}` wrapper
   - Extracts `data[0].content` → text content
   - Extracts `data[0].buttons` → JSON string or list of `{title, payload}` objects
4. Returns `{"content": str, "buttons": List[Dict]}`

#### Build Response

```python
service_buttons = service_result["buttons"]
buttons_list = [ChoiceButton(**b) for b in service_buttons if "title" in b and "payload" in b]

return OrchestrationResponse(
    chatId=request.chatId,
    llmServiceActive=True,
    questionOutOfLLMScope=False,
    inputGuardFailed=False,
    content=service_content,
    buttons=buttons_list if buttons_list else None,
)
```

### 1.5 API Layer — Response Conversion

Back in `test_orchestrate_llm_request()` (line 382):

```python
test_response = TestOrchestrationResponse(
    llmServiceActive=response.llmServiceActive,
    questionOutOfLLMScope=response.questionOutOfLLMScope,
    inputGuardFailed=response.inputGuardFailed,
    content=response.content,
    buttons=response.buttons,   # ← forwarded
    chunks=None,
)
```

### 1.6 Frontend — Display Result

**`TestModel/index.tsx`**:

```tsx
// onSuccess callback (line 51-54)
setInferenceResult(data?.response);
setPendingButtons(data?.response?.buttons ?? []);
```

- Response text is rendered inside `<ReactMarkdown>` (line 166-168)
- MCQ buttons are rendered if `pendingButtons.length > 0` (line 173-186):

```tsx
{pendingButtons.map((btn) => (
  <Button
    key={btn.payload}
    appearance={ButtonAppearanceTypes.SECONDARY}
    onClick={() => handleButtonClick(btn.payload)}
  >
    {btn.title}
  </Button>
))}
```

---

## Flow 2: MCQ Button Click (Direct Step — Short-Circuit)

### 2.1 Frontend — Button Click

When the user clicks a button (e.g., *[Windows]*), `handleButtonClick()` is called (line 81):

```tsx
const handleButtonClick = (payload: string) => {
  if (!testLLM.connectionId) return;
  setPendingButtons([]);
  inferenceMutation.mutate({
    llmConnectionId: Number(testLLM.connectionId),
    message: payload,  // e.g. "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0"
  });
};
```

The button **payload** becomes the next message. The same API call (`/rag-search/inference/test` → `/orchestrate/test`) is made.

### 2.2 Input Sanitizer Safety

The `#service, /POST/...` payload goes through Pydantic's `validate_and_sanitize_message()` on `OrchestrationRequest.message` (line 64-88 of `request_models.py`). The `InputSanitizer.sanitize_message()` strips HTML tags and normalizes whitespace but leaves `#`, `,`, `/` characters intact. The payload passes through unchanged.

### 2.3 Orchestration — `#service` Prefix Short-Circuit

**`process_orchestration_request()`** (line 324-340):

```python
# STEP 0.1: Multi-step service prefix check (bypass NLU pipeline)
if request.message.startswith(SERVICE_STEP_PREFIXES):
    logger.info(f"[{request.chatId}] #service prefix detected - direct step execution")
    executor = self._get_service_workflow_executor()
    direct_response = await executor.execute_direct_step(
        request=request,
        time_metric=time_metric,
    )
    if direct_response is not None:
        log_step_timings(time_metric, request.chatId)
        return direct_response
```

**`SERVICE_STEP_PREFIXES`** = `("#service,", "#common_service,")` from `constants.py`.

**`_get_service_workflow_executor()`** (line 264):
- Reuses the existing `tool_classifier.service_workflow` if a ToolClassifier has been initialized
- Otherwise creates a lightweight `ServiceWorkflowExecutor(llm_manager=None, orchestration_service=self)` — no LLM is needed for direct steps

### 2.4 ServiceWorkflowExecutor — `execute_direct_step()`

**`service_workflow.py` → `execute_direct_step()`** (line 1000):

1. **Parse**: `_parse_service_prefix(request.message)`
   - Input: `"#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0"`
   - Splits off prefix → remainder: `/POST/services/active/...`
   - Extracts HTTP method: `POST`
   - Builds URL: `http://ruuter:8086/services/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0`
   - Returns: `("POST", "http://ruuter:8086/services/services/active/...")`

2. **Call endpoint**: `_call_service_endpoint(url, "POST", [], chat_id, author_id)`
   - `entities_array=[]` — no entities for MCQ steps
   - Same parsing as Flow 1 (extracts `content` + `buttons`)

3. **Build response**: Same `OrchestrationResponse` construction as Flow 1

### What Gets Skipped (Short-Circuit)

| Skipped Step | Why |
|---|---|
| Query validation | Would reject `#service` as gibberish |
| Component initialization | Expensive (LLM manager, Vault, guardrails) |
| Input guardrails | Would block a machine-generated payload |
| ToolClassifier.classify() | LLM call — unnecessary cost |
| Intent detection LLM | Another LLM call — URL is already known |
| Entity extraction | No natural language entities to extract |
| Semantic search (Qdrant) | No need to find a service |

### 2.5 Response & Loop

The response follows the same path back through `test_orchestrate_llm_request()` → frontend.

- If the response has `buttons` → frontend renders the next set of MCQ buttons
- If the response has `buttons=null` → the MCQ flow is complete, only the final text answer is shown

---

## Data Models

### Request

```python
class TestOrchestrationRequest:
    message: str
    environment: Literal["production", "testing", "development"]
    connectionId: Optional[int]
```

### Response

```python
class TestOrchestrationResponse:
    llmServiceActive: bool
    questionOutOfLLMScope: bool
    inputGuardFailed: bool
    content: str
    buttons: Optional[List[ChoiceButton]]  # MCQ buttons
    chunks: Optional[List[ChunkInfo]]      # RAG context chunks

class ChoiceButton:
    title: str    # "Windows"
    payload: str  # "#service, /POST/services/active/..."
```

---

## Complete MCQ Sequence Diagram

```
User              TestModel UI             API (/orchestrate/test)       ServiceWorkflow         Ruuter/DMapper
  │                    │                         │                            │                       │
  │ types "keyboard    │                         │                            │                       │
  │  not working"      │                         │                            │                       │
  ├───────────────────▶│  POST inference/test     │                            │                       │
  │                    ├────────────────────────▶│  process_orchestration_     │                       │
  │                    │                         │  request()                  │                       │
  │                    │                         │  startswith(#service)?→NO   │                       │
  │                    │                         │  classify()→SERVICE         │                       │
  │                    │                         ├───────────────────────────▶│ execute_async()        │
  │                    │                         │                            │ intent detect→matched  │
  │                    │                         │                            │ _call_service_endpoint │
  │                    │                         │                            ├──────────────────────▶│
  │                    │                         │                            │◁ {content,buttons}─────│
  │                    │                         │◁─ OrchestrationResponse ───│                       │
  │                    │◁─ TestOrchResponse ─────│                            │                       │
  │◁─ render text +    │                         │                            │                       │
  │   [Windows] [Mac]  │                         │                            │                       │
  │                    │                         │                            │                       │
  │ clicks [Windows]   │                         │                            │                       │
  ├───────────────────▶│  POST inference/test     │                            │                       │
  │                    │  msg="#service,/POST/…"  │                            │                       │
  │                    ├────────────────────────▶│  startswith(#service)?→YES  │                       │
  │                    │                         │  SKIP classifier+guardrails│                       │
  │                    │                         ├───────────────────────────▶│ execute_direct_step() │
  │                    │                         │                            │ _parse_service_prefix  │
  │                    │                         │                            │ _call_service_endpoint │
  │                    │                         │                            ├──────────────────────▶│
  │                    │                         │                            │◁ {content,buttons}─────│
  │                    │                         │◁─ OrchestrationResponse ───│                       │
  │                    │◁─ TestOrchResponse ─────│                            │                       │
  │◁─ render next MCQ  │                         │                            │                       │
  │   or final answer  │                         │                            │                       │
```

---

## Error Handling

| Error Scenario | Behavior |
|---|---|
| Service discovery fails | `execute_async()` returns `None` → falls back to RAG/context pipeline |
| Intent detection fails | Returns `None` → falls back to RAG/context pipeline |
| `_parse_service_prefix()` fails | `execute_direct_step()` returns `None` → falls through to normal pipeline |
| Service endpoint timeout | `_call_service_endpoint()` returns `None` → falls back |
| Service endpoint HTTP error | Logged, returns `None` → falls back |
| Buttons JSON parsing fails | Logs warning, returns empty buttons list `[]` |
