# Multi-Step Service Support — Implementation Plan

## Part 1: Current State, Gaps, and Expected Outcome

### Background

The existing service workflow supports **single-step service triggering**: an LLM detects intent from a user's natural language message, extracts entities, and calls a Ruuter service endpoint exactly once. The response is a plain text string returned to the user.

In the Bürokratt ecosystem, many services are **multi-step flows**. After a first service call, the response contains not just text but also a set of choice buttons. Each button carries a hidden `#service` payload (e.g. `#service, /POST/services/active/application_mcq_step_passport`). When the user clicks a button, that payload string becomes the next message. The system must recognize this prefix, skip all NLU processing, and call the next step endpoint directly.

This document defines every change needed to make the RAG module's service workflow support these multi-step / MCQ flows end-to-end, covering both the `/orchestrate` and `/orchestrate/stream` endpoints.

---

### Identified Gaps

#### Gap 1 — No `#service` Prefix Detection (Short-Circuit Path)
**Affected files:** `src/llm_orchestration_service.py`  
**Methods:** `process_orchestration_request()`, `stream_orchestration_response()`

When a button payload like `#service, /POST/services/active/application_mcq_step_passport` arrives as the user message, it goes through the full pipeline: language detection → query validation → guardrails → tool classifier → hybrid search → intent detection LLM → entity extraction. This is wrong in two ways: (a) the LLM steps waste time and cost on a message that is a machine-generated command, not natural language; (b) guardrails may reject it as malformed input, breaking the flow entirely.

**Expected after fix:** A check at the very top of both methods detects the `#service` or `#common_service` prefix and immediately routes to a direct service trigger path, bypassing query validation, guardrails, classifier, and intent detection.

---

#### Gap 2 — No `#service` Payload Parser
**Affected files:** `src/tool_classifier/workflows/service_workflow.py`

The string `#service, /POST/services/active/application_mcq_step_passport` encodes the HTTP method and path. There is currently no code that splits this string to extract `POST` and `/services/active/application_mcq_step_passport`. The existing `_construct_service_endpoint()` only builds URLs from a `service_name` string obtained from the service registry — it cannot handle a pre-formed path from a button payload.

**Expected after fix:** A new parser method `_parse_service_prefix(payload: str)` returns `(http_method, endpoint_url)` by splitting the `#service,` prefix and interpreting the embedded HTTP verb and path. A corresponding new entry-point method `execute_direct_step()` (for non-streaming) and `execute_direct_step_streaming()` (for streaming) calls this parser and directly invokes the endpoint without any discovery or intent detection.

---

#### Gap 3 — `_call_service_endpoint` Returns Only the First Text Item
**Affected files:** `src/tool_classifier/workflows/service_workflow.py`  
**Method:** `_call_service_endpoint()`

The current implementation does `data[0].get("content", "")` — it reads only the first element of the DMapper response array and returns a plain string. For multi-step services the DMapper array contains both the text message (item 0) and button definitions (items 1+). This data is silently dropped, making it impossible to render the next MCQ step in the UI.

**Expected after fix:** The method returns the full structured response — specifically the entire response array or a structured dict containing `text` and `buttons`. The caller is responsible for assembling this into the API response.

---

#### Gap 4 — `OrchestrationResponse.content` Is a Plain String, No Buttons Field
**Affected files:** `src/models/request_models.py`

`OrchestrationResponse` has `content: str`. There is no field to carry button choices. The frontend cannot render MCQ buttons if they are not present in the response.

**Expected after fix:** A new optional field `buttons: Optional[List[Dict[str, Any]]]` is added to `OrchestrationResponse`. For regular RAG/context/single-step service responses this field is `None` (no change to existing behavior). For MCQ step responses it carries the button array. Button shape follows the DMapper structure: `[{"title": "Passport", "payload": "#service, /POST/services/active/..."}]`.

---

#### Gap 5 — SSE `format_sse` Cannot Carry Structured Button Data
**Affected files:** `src/llm_orchestration_service.py`  
**Method:** `format_sse()`

The current SSE payload is:
```json
{"chatId": "...", "payload": {"content": "token_string"}, "timestamp": "...", "sentTo": []}
```
There is no slot for buttons. The streaming service workflow (`execute_streaming` in `service_workflow.py`) emits a single `format_sse(chat_id, service_content)` call where `service_content` is already a plain string — buttons are already lost before reaching this point.

**Expected after fix:** `format_sse` gains an optional `buttons` parameter. When provided, it is included in `payload` alongside `content`:
```json
{"chatId": "...", "payload": {"content": "...", "buttons": [...]}, "timestamp": "...", "sentTo": []}
```
All existing non-MCQ call sites pass no `buttons` argument so behavior is unchanged.

---

#### Gap 6 — `TestOrchestrationResponse` Conversion Drops `buttons`
**Affected files:** `src/llm_orchestration_service_api.py`  
**Handler:** `/orchestrate/test`

The test endpoint explicitly copies fields from `OrchestrationResponse` to `TestOrchestrationResponse`:
```python
test_response = TestOrchestrationResponse(
    llmServiceActive=response.llmServiceActive,
    ...
    content=response.content,
    chunks=None,
)
```
Once `buttons` is added to `OrchestrationResponse`, this field will be silently dropped in test mode.

**Expected after fix:** `TestOrchestrationResponse` also gets a `buttons` field, and the copy block in the test handler forwards it.

---

#### Gap 7 — Input Sanitizer May Mangle `#service` Payloads
**Affected files:** `src/utils/input_sanitizer.py`, `src/models/request_models.py`

`sanitize_message()` strips HTML tags and normalizes whitespace. The `#service, /POST/services/active/application_mcq_step_passport` string contains `/`, `,`, `#` characters that are not HTML and will pass through `strip_html_tags` safely. However, this needs to be **verified** against the actual regex in `strip_html_tags` before implementing the bypass, because if the sanitizer runs before the prefix check it could subtly alter the string. Since the prefix bypass (Gap 1) is inserted **before** component initialization and the sanitizer runs inside the Pydantic validator at model construction time (before any Python handler runs), the `#service` string will always be sanitized first. The sanitizer must leave it intact.

**Expected after fix:** Confirm via a test that `InputSanitizer.sanitize_message("#service, /POST/services/active/application_mcq_step_passport")` returns the string unchanged.

---

#### Gap 8 — No Ruuter DSL Bypass for MCQ Step Paths
**Affected files:** `DSL/Ruuter.public/`

In the reference project, service paths containing `_mcq_` or prefixed with `common_service` automatically bypass the `service_trigger` approval database check. This project's DSL does not yet implement this bypass. Without it, calling an MCQ step endpoint via Ruuter may return `"Service is not approved"`.

**Expected after fix:** Ruuter DSL logic (the `chats/trigger-service` template equivalent) is updated to skip the approval lookup when the path matches `_mcq_` or `common_service` patterns, consistent with the reference project.

---

### What the Full Flow Looks Like After All Fixes

```
FIRST TURN (natural language → service detection, unchanged)
User: "I want to check my application status"
  → Language detection → Query validation → Input guardrails
  → ToolClassifier.classify() → SERVICE workflow
  → Intent detection LLM → entity extraction
  → _construct_service_endpoint() + _call_service_endpoint()
  → DMapper returns [text_item, button_item_1, button_item_2]
  → OrchestrationResponse(content="Which type?", buttons=[{...}, {...}])
  → Frontend renders text + [Passport] [ID Card] buttons

SUBSEQUENT TURNS (button click → direct step, new path)
User clicks [Passport] → message = "#service, /POST/services/active/application_mcq_step_passport"
  → [NEW] Prefix detected → skip validation/guardrails/classifier/LLM entirely
  → [NEW] _parse_service_prefix() → method=POST, url=.../application_mcq_step_passport
  → [NEW] execute_direct_step() → _call_service_endpoint()
  → DMapper returns [text_item, button_item_1, button_item_2] (next MCQ step)
  → OrchestrationResponse(content="Which year?", buttons=[{2023}, {2024}])
  → Frontend renders next MCQ step

  (Loop repeats until no buttons returned → final answer)
```

---

## Part 2: Task List (Priority Order)

---

### TASK-01 · Verify Input Sanitizer Safety for `#service` Payloads
**Priority:** P0 — Blocker; must be confirmed before any code changes  
**File:** `src/utils/input_sanitizer.py`  
**Type:** Investigation + unit test

The Pydantic model validator on `OrchestrationRequest.message` runs `sanitize_message()` at HTTP request parse time — before any handler code runs. If the sanitizer alters the `#service, /POST/...` string (e.g. collapses whitespace after the comma, or strips the `#`), the prefix detection logic in Task-03 will never match.

**Work:**
1. Read `strip_html_tags()` implementation and confirm `#`, `,`, `/` are not affected.
2. Add a unit test: `assert InputSanitizer.sanitize_message("#service, /POST/services/active/foo") == "#service, /POST/services/active/foo"`.
3. If the sanitizer does alter it, add a passthrough rule for the `#service` prefix before stripping HTML.

---

### TASK-02 · Add `buttons` Field to `OrchestrationResponse` and `TestOrchestrationResponse`
**Priority:** P1 — Foundation; all other tasks depend on this data shape  
**File:** `src/models/request_models.py`  
**Type:** Model change

`OrchestrationResponse` needs a new optional field:
```python
buttons: Optional[List[Dict[str, Any]]] = Field(
    default=None,
    description="Optional list of choice buttons for MCQ step responses"
)
```
`TestOrchestrationResponse` needs the same field so the test endpoint does not silently drop button data.

Button dict shape matches the DMapper output:
```python
{"title": "Button label shown to user", "payload": "#service, /POST/services/active/step_name"}
```

**Work:**
1. Add `buttons` field to `OrchestrationResponse`.
2. Add `buttons` field to `TestOrchestrationResponse`.
3. Confirm existing tests still pass (field is `Optional`, defaults to `None`, no breaking change).

---

### TASK-03 · Update `_call_service_endpoint` to Return Full Structured Response
**Priority:** P1 — Must be done before building the direct-step executor  
**File:** `src/tool_classifier/workflows/service_workflow.py`  
**Method:** `_call_service_endpoint()`  
**Type:** Return type change

Current return: `Optional[str]` (only `data[0]["content"]`).  
New return: `Optional[Dict[str, Any]]` with shape `{"content": str, "buttons": List[Dict]}`.

The full DMapper array may look like:
```json
[
  {"content": "Which application type?"},
  {"title": "Passport", "payload": "#service, /POST/services/active/application_mcq_step_passport"},
  {"title": "ID Card", "payload": "#service, /POST/services/active/application_mcq_step_id"}
]
```
The method should return:
```python
{
    "content": data[0].get("content", ""),
    "buttons": data[1:]   # empty list if single-step service
}
```

**Work:**
1. Change return type annotation from `Optional[str]` to `Optional[Dict[str, Any]]`.
2. Update the response parsing block to extract all items and separate text from buttons.
3. Update both `execute_async()` and `execute_streaming()` callers inside `ServiceWorkflowExecutor` to read `result["content"]` and `result["buttons"]` rather than using the string directly.
4. Update `OrchestrationResponse` construction in both execute methods to pass `buttons=result["buttons"]`.

---

### TASK-04 · Update `format_sse` to Carry Optional Buttons
**Priority:** P1 — Required for streaming endpoint to deliver buttons to the frontend  
**File:** `src/llm_orchestration_service.py`  
**Method:** `format_sse()`  
**Also:** Protocol definition in `src/tool_classifier/workflows/service_workflow.py` (`LLMServiceProtocol.format_sse`)  
**Type:** Method signature extension

Add an optional `buttons` parameter:
```python
def format_sse(
    self,
    chat_id: str,
    content: str,
    buttons: Optional[List[Dict[str, Any]]] = None,
) -> str:
```
When `buttons` is not `None` and not empty, include it in the payload:
```python
payload = {
    "chatId": chat_id,
    "payload": {"content": content, **({"buttons": buttons} if buttons else {})},
    "timestamp": ...,
    "sentTo": [],
}
```
All existing call sites pass no `buttons` argument — no behavior change for RAG/context/single-step flows.

**Work:**
1. Update `format_sse` signature and body in `llm_orchestration_service.py`.
2. Update the `LLMServiceProtocol.format_sse` stub in `service_workflow.py` to match.
3. Update the `service_stream()` async generator in `execute_streaming()` to call `format_sse(chat_id, result["content"], result["buttons"])`.

---

### TASK-05 · Add `#service` Prefix Parser to `ServiceWorkflowExecutor`
**Priority:** P2 — Prerequisite for Task-06  
**File:** `src/tool_classifier/workflows/service_workflow.py`  
**Type:** New method

Add a static method `_parse_service_prefix(payload: str) -> Optional[tuple[str, str]]` that:
1. Strips the `#service,` or `#common_service,` prefix.
2. Splits the remainder on the first `/` to extract the HTTP method (e.g. `POST`, `GET`).
3. Constructs the full Ruuter URL: `{RUUTER_SERVICE_BASE_URL}{path}`.
4. Returns `(http_method, full_url)` or `None` if the format is unrecognised.

Example:
```
Input:  "#service, /POST/services/active/application_mcq_step_passport"
Output: ("POST", "http://ruuter:8086/services/active/application_mcq_step_passport")
```

Also add a module-level constant:
```python
SERVICE_STEP_PREFIXES = ("#service,", "#common_service,")
```

**Work:**
1. Add `SERVICE_STEP_PREFIXES` constant to `src/tool_classifier/constants.py`.
2. Implement `_parse_service_prefix()` as a `@staticmethod` on `ServiceWorkflowExecutor`.
3. Add unit test covering: valid POST, valid GET, `#common_service` prefix, malformed input → `None`.

---

### TASK-06 · Add Direct Step Executor Methods to `ServiceWorkflowExecutor`
**Priority:** P2 — Core of the multi-step execution path  
**File:** `src/tool_classifier/workflows/service_workflow.py`  
**Type:** New methods

Add two new methods:

**`execute_direct_step(request, time_metric) -> Optional[OrchestrationResponse]`**  
Used by the non-streaming path. Calls `_parse_service_prefix(request.message)`, then calls `_call_service_endpoint()` directly (no discovery, no intent detection, no entity extraction — the URL is already known). Returns a populated `OrchestrationResponse` with `content` and `buttons` from the structured result.

**`execute_direct_step_streaming(request, time_metric) -> Optional[AsyncIterator[str]]`**  
Used by the streaming path. Same logic but wraps the response in the SSE generator:
```python
async def step_stream():
    yield orchestration_service.format_sse(chat_id, result["content"], result["buttons"])
    yield orchestration_service.format_sse(chat_id, "END")
```

Both methods must log `[chat_id] DIRECT STEP: {url}` and return `None` if parsing fails (to allow graceful fallback).

**Work:**
1. Implement `execute_direct_step()`.
2. Implement `execute_direct_step_streaming()`.
3. Add unit tests for both (mock `_call_service_endpoint`).

---

### TASK-07 · Add `#service` Prefix Short-Circuit to `process_orchestration_request`
**Priority:** P3 — Connects the direct executor to the non-streaming endpoint  
**File:** `src/llm_orchestration_service.py`  
**Method:** `process_orchestration_request()`  
**Type:** Control flow addition

Insert a check **before** STEP 0.5 (query validation). The check must be the very first logic after language detection:

```python
# STEP 0.1: Multi-step service prefix check (bypass NLU pipeline)
if request.message.startswith(SERVICE_STEP_PREFIXES):
    logger.info(f"[{request.chatId}] #service prefix detected - direct step execution")
    if self.service_workflow_executor is None:
        # initialize with llm_manager if needed
        ...
    response = await self.service_workflow_executor.execute_direct_step(
        request=request,
        time_metric=time_metric,
    )
    if response is not None:
        return response
    # If parsing failed, fall through to normal pipeline (safe degradation)
```

`SERVICE_STEP_PREFIXES` is the constant added in Task-05, imported here.

Note: Language detection is still allowed to run first (it is cheap and needed for potential error messages from the fallback path).

**Work:**
1. Import `SERVICE_STEP_PREFIXES` from `tool_classifier.constants`.
2. Add the prefix check block immediately after language detection.
3. Ensure the `service_workflow_executor` instance is either reused from the tool classifier or lazily initialized.
4. Add integration test: send `#service, /POST/services/active/test_step` to the non-streaming path and verify it skips guardrails + classifier.

---

### TASK-08 · Add `#service` Prefix Short-Circuit to `stream_orchestration_response`
**Priority:** P3 — Connects the direct executor to the streaming endpoint  
**File:** `src/llm_orchestration_service.py`  
**Method:** `stream_orchestration_response()`  
**Type:** Control flow addition

Same logic as Task-07 but for the streaming generator. The check must be inserted **before** the query validation `yield` block, after language detection:

```python
# STEP 0.1: Multi-step service prefix check (bypass NLU pipeline)
if request.message.startswith(SERVICE_STEP_PREFIXES):
    logger.info(f"[{request.chatId}] #service prefix detected - direct step stream")
    step_stream = await self.service_workflow_executor.execute_direct_step_streaming(
        request=request,
        time_metric=time_metric,
    )
    if step_stream is not None:
        async for chunk in step_stream:
            yield chunk
        stream_ctx.mark_completed()
        return
    # If None, fall through to normal pipeline
```

**Work:**
1. Add the prefix check block immediately after language detection inside the streaming generator.
2. Verify stream timeout wrapper in the API layer still applies (it wraps the entire generator so it applies automatically — no change needed in the API file).
3. Add integration test: send `#service` payload to the streaming path and verify SSE stream delivers `content` + `buttons` + `END`.

---

### TASK-09 · Forward `buttons` in `/orchestrate/test` Conversion Block
**Priority:** P4 — Correctness fix in the API layer  
**File:** `src/llm_orchestration_service_api.py`  
**Handler:** `test_orchestrate_llm_request()`  
**Type:** Bug fix (future)

The explicit field copy from `OrchestrationResponse` to `TestOrchestrationResponse` must include `buttons` once that field exists (added in Task-02):

```python
test_response = TestOrchestrationResponse(
    llmServiceActive=response.llmServiceActive,
    questionOutOfLLMScope=response.questionOutOfLLMScope,
    inputGuardFailed=response.inputGuardFailed,
    content=response.content,
    buttons=response.buttons,   # <-- add this
    chunks=None,
)
```

**Work:**
1. After Task-02 is complete, add `buttons=response.buttons` to this copy block.
2. This is a one-line change but must not be forgotten — without it, the test endpoint silently drops button data.

---

### TASK-10 · Update Ruuter DSL to Bypass Approval for MCQ Step Paths
**Priority:** P4 — Infrastructure; can be done in parallel with code changes  
**Files:** `DSL/Ruuter.public/` (specifically the `chats/trigger-service` equivalent DSL)  
**Type:** DSL / configuration change

Without this, the Ruuter gateway may reject MCQ step calls with `"Service is not approved"` because they are not registered in the `service_trigger` approval table.

Add a condition in the DSL that skips the approval database lookup when:
- The service path contains `_mcq_`  
- **OR** the prefix is `common_service`

This mirrors the reference project's logic exactly.

**Work:**
1. Identify the DSL file that performs the `service_trigger` database check.
2. Add an `if` branch: if path contains `_mcq_` or `common_service` → skip approval check, proceed directly to HTTP call.
3. Test with a mock MCQ step endpoint to confirm the bypass works.

---

### TASK-11 · End-to-End Integration Test for Multi-Step Flow
**Priority:** P5 — Validation; done last  
**Files:** `tests/integration_tests/`  
**Type:** New test

Add a full flow integration test:
1. First turn: natural language message → service detected → response contains `buttons`.
2. Second turn: send `buttons[0]["payload"]` as the user message → verify no LLM call made, correct step endpoint called, new `buttons` in response.
3. Final turn: send final step → verify response has `buttons=None` or empty list.

Requires mock Ruuter service endpoint or test container setup.

---

### Summary Table

| Task | Description | Priority | File(s) |
|------|-------------|----------|---------|
| TASK-01 | Verify sanitizer safety for `#service` strings | P0 | `utils/input_sanitizer.py` |
| TASK-02 | Add `buttons` field to response models | P1 | `models/request_models.py` |
| TASK-03 | `_call_service_endpoint` returns full structured response | P1 | `service_workflow.py` |
| TASK-04 | `format_sse` carries optional buttons | P1 | `llm_orchestration_service.py` |
| TASK-05 | `#service` payload parser + constants | P2 | `service_workflow.py`, `constants.py` |
| TASK-06 | Direct step executor methods (sync + streaming) | P2 | `service_workflow.py` |
| TASK-07 | Prefix short-circuit in `process_orchestration_request` | P3 | `llm_orchestration_service.py` |
| TASK-08 | Prefix short-circuit in `stream_orchestration_response` | P3 | `llm_orchestration_service.py` |
| TASK-09 | Forward `buttons` in `/orchestrate/test` copy block | P4 | `llm_orchestration_service_api.py` |
| TASK-10 | Ruuter DSL bypass for MCQ step paths | P4 | `DSL/Ruuter.public/` |
| TASK-11 | End-to-end integration test | P5 | `tests/integration_tests/` |
