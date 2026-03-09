# Context Workflow: Greeting Detection and Conversation History Analysis

## Overview

The **Context Workflow (Layer 2)** intercepts user queries that can be answered without searching the knowledge base. It handles two categories:

1. **Greetings** — Detects and responds to social exchanges (hello, goodbye, thanks) in multiple languages
2. **Conversation history references** — Answers follow-up questions that refer to information already discussed in the session

When the context workflow can answer, a response is returned immediately, bypassing the RAG pipeline entirely. When it cannot answer, the query falls through to the RAG workflow (Layer 3).

---

## Architecture

### Position in the Classifier Chain

```
User Query
    ↓
Layer 1: SERVICE   → External API calls
    ↓ (cannot handle)
Layer 2: CONTEXT   → Greetings + conversation history  ←── This document
    ↓ (cannot handle)
Layer 3: RAG       → Knowledge base retrieval
    ↓ (cannot handle)
Layer 4: OOD       → Out-of-domain fallback
```

### Key Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `ContextAnalyzer` | `src/tool_classifier/context_analyzer.py` | LLM-based greeting detection and context analysis |
| `ContextWorkflowExecutor` | `src/tool_classifier/workflows/context_workflow.py` | Orchestrates the workflow, handles streaming/non-streaming |
| `ToolClassifier` | `src/tool_classifier/classifier.py` | Invokes `ContextAnalyzer` during classification and routes to `ContextWorkflowExecutor` |
| `greeting_constants.py` | `src/tool_classifier/greeting_constants.py` | Fallback greeting responses for Estonian and English |

---

## Full Request Flow

```
User Query + Conversation History
    ↓
ToolClassifier.classify()
    ├─ Layer 1 (SERVICE): Embedding-based intent routing
    │      └─ If no service tool matches → route to CONTEXT workflow
    │
    └─ ClassificationResult(workflow=CONTEXT)

ToolClassifier.route_to_workflow()
    ├─ Non-streaming → ContextWorkflowExecutor.execute_async()
    │      ├─ Phase 1: _detect() → context_analyzer.detect_context() [classification only]
    │      ├─ If greeting → return greeting OrchestrationResponse
    │      ├─ If can_answer → _generate_response_async() → context_analyzer.generate_context_response()
    │      └─ Otherwise → return None (RAG fallback)
    │
    └─ Streaming → ContextWorkflowExecutor.execute_streaming()
           ├─ Phase 1: _detect() → context_analyzer.detect_context() [classification only]
           ├─ If greeting → _stream_greeting() async generator
           ├─ If can_answer → _create_history_stream() → context_analyzer.stream_context_response()
           └─ Otherwise → return None (RAG fallback)
```

---

## Phase 1: Detection (Classify Only)

### LLM Task

Every query is checked against the **most recent 10 conversation turns** using a single LLM call (`detect_context()`). This phase **does not generate an answer** — it only classifies the query and extracts a relevant context snippet for Phase 2.

The `ContextDetectionSignature` DSPy signature instructs the LLM to:

1. Detect if the query is a greeting in any supported language
2. Check if the query references something discussed in the last 10 turns
3. If the query can be answered from history, extract the relevant snippet
4. Do **not** generate the final answer here — detection only

### LLM Output Format

The LLM returns a JSON object parsed into `ContextDetectionResult`:

```json
{
  "is_greeting": false,
  "can_answer_from_context": true,
  "reasoning": "User is asking about tax rate discussed earlier",
  "context_snippet": "Bot confirmed the flat rate is 20%, applying equally to all income brackets."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `is_greeting` | `bool` | Whether the query is a greeting |
| `can_answer_from_context` | `bool` | Whether the query can be answered from conversation history |
| `reasoning` | `str` | Brief explanation of the detection decision |
| `context_snippet` | `str \| null` | Relevant excerpt from history for use in Phase 2, or `null` |

> **Internal field**: `answered_from_summary` (bool, default `False`) is reserved for future summary-based detection paths.

### Decision After Phase 1

```
is_greeting=True                              → Phase 2: return greeting response (no LLM call)
can_answer_from_context=True AND snippet set  → Phase 2: generate answer from snippet
Otherwise                                     → Fall back to RAG
```

---

## Phase 2: Response Generation

### Non-Streaming (`_generate_response_async`)

Calls `generate_context_response(query, context_snippet)` which uses `ContextResponseGenerationSignature` to produce a complete answer in a single LLM call. Output guardrails are applied before returning the `OrchestrationResponse`.

### Streaming (`_create_history_stream` → `stream_context_response`)

Calls `stream_context_response(query, context_snippet)` which uses DSPy native streaming (`dspy.streamify`) with `ContextResponseGenerationSignature`. Tokens are yielded in real time and passed through NeMo Guardrails before being SSE-formatted.

---

---

## Greeting Detection

### Supported Languages

| Language | Code |
|----------|------|
| Estonian | `et` |
| English | `en` |

### Supported Greeting Types

| Type | Estonian Examples | English Examples |
|------|-------------------|-----------------|
| `hello` | Tere, Hei, Tervist, Moi | Hello, Hi, Hey, Good morning |
| `goodbye` | Nägemist, Tšau | Bye, Goodbye, See you, Good night |
| `thanks` | Tänan, Aitäh, Tänud | Thank you, Thanks |
| `casual` | Tere, Tervist | Hey |

### Greeting Response Generation

The LLM generates contextually appropriate responses in the **same language** as the query. If the LLM detects a greeting but fails to produce an answer (e.g., JSON parse error), the system falls back to predefined static responses from `greeting_constants.py`.

**Fallback responses (`greeting_constants.py`):**

```python
GREETINGS_ET = {
    "hello":   "Tere! Kuidas ma saan sind aidata?",
    "goodbye": "Nägemist! Head päeva!",
    "thanks":  "Palun! Kui on veel küsimusi, küsi julgelt.",
    "casual":  "Tere! Mida ma saan sinu jaoks teha?",
}

GREETINGS_EN = {
    "hello":   "Hello! How can I help you?",
    "goodbye": "Goodbye! Have a great day!",
    "thanks":  "You're welcome! Feel free to ask if you have more questions.",
    "casual":  "Hey! What can I do for you?",
}
```

The fallback greeting type is determined by keyword matching in `_detect_greeting_type()` — checking for `thank/tänan/aitäh`, `bye/goodbye/nägemist/tšau`, before defaulting to `hello`.

---

## Streaming Support

The context workflow supports both response modes:

### Non-Streaming (`execute_async`)

Returns a complete `OrchestrationResponse` object with the answer as a single string. Output guardrails are applied before the response is returned.

### Streaming (`execute_streaming`)

Returns an `AsyncIterator[str]` that yields SSE (Server-Sent Events) chunks.

**Greeting responses** are yielded as a single SSE chunk followed by `END`.

**History responses** use DSPy native streaming (`dspy.streamify`) with `ContextResponseGenerationSignature`. Tokens are emitted in real time as they arrive from the LLM, then passed through NeMo Guardrails (`stream_with_guardrails`) before being SSE-formatted. If a guardrail violation is detected in a chunk, streaming stops and the violation message is sent instead.

**SSE Format:**
```
data: {"chatId": "abc123", "payload": {"content": "Tere! Kuidas ma"}, "timestamp": "...", "sentTo": []}

data: {"chatId": "abc123", "payload": {"content": " saan sind aidata?"}, "timestamp": "...", "sentTo": []}

data: {"chatId": "abc123", "payload": {"content": "END"}, "timestamp": "...", "sentTo": []}
```

---

## Cost Tracking

LLM token usage and cost is tracked via `get_lm_usage_since()` and stored in `costs_metric` within the workflow executor. Costs are logged via `orchestration_service.log_costs()` at the end of each execution path.

Two cost keys are tracked separately:

```python
costs_metric = {
    "context_detection": {
        # Phase 1: detect_context() — single LLM call
        "total_cost": 0.0012,
        "total_tokens": 180,
        "total_prompt_tokens": 150,
        "total_completion_tokens": 30,
        "num_calls": 1,
    },
    "context_response": {
        # Phase 2: generate_context_response() or stream_context_response()
        "total_cost": 0.003,
        "total_tokens": 140,
        "total_prompt_tokens": 100,
        "total_completion_tokens": 40,
        "num_calls": 1,
    },
}
```

Greeting responses skip Phase 2, so only `"context_detection"` cost is populated.

---

---

## Error Handling and Fallback

| Failure Point | Behaviour |
|---------------|-----------|
| Phase 1 LLM call raises exception | `can_answer_from_context=False` → falls back to RAG |
| Phase 1 returns invalid JSON | Logged as warning, all flags default to `False` → falls back to RAG |
| Phase 2 LLM call raises exception | Logged as error, `_generate_response_async` returns `None` → falls back to RAG |
| Phase 2 returns empty answer | Logged as warning → falls back to RAG |
| Output guardrails fail | Logged as warning, response returned without guardrail check |
| Guardrail violation in streaming | `OUTPUT_GUARDRAIL_VIOLATION_MESSAGE` sent, stream terminated |
| `orchestration_service` unavailable | History streaming skipped → `None` returned → RAG fallback |
| `guardrails_adapter` not a `NeMoRailsAdapter` | Logged as warning → cannot stream → RAG fallback |
| Any unhandled exception in executor | Error logged, `execute_async/execute_streaming` returns `None` → RAG fallback via classifier |

---

## Logging

Key log entries emitted during a request:

| Level | Message | When |
|-------|---------|------|
| `INFO` | `CONTEXT WORKFLOW (NON-STREAMING) \| Query: '...'` | `execute_async()` entry |
| `INFO` | `CONTEXT WORKFLOW (STREAMING) \| Query: '...'` | `execute_streaming()` entry |
| `INFO` | `CONTEXT DETECTOR: Phase 1 \| Query: '...' \| History: N turns` | `detect_context()` entry |
| `INFO` | `DETECTION RESULT \| Greeting: ... \| Can Answer: ... \| Has snippet: ...` | Phase 1 LLM response parsed |
| `INFO` | `Detection cost \| Total: $... \| Tokens: N` | After Phase 1 cost tracked |
| `INFO` | `Detection: greeting=... can_answer=...` | After `_detect()` returns in executor |
| `INFO` | `CONTEXT GENERATOR: Phase 2 non-streaming \| Query: '...'` | `generate_context_response()` entry |
| `INFO` | `CONTEXT GENERATOR: Phase 2 streaming \| Query: '...'` | `stream_context_response()` entry |
| `INFO` | `Context response streaming complete (final Prediction received)` | DSPy streaming finished |
| `WARNING` | `[chatId] Phase 2 empty answer — fallback to RAG` | Phase 2 returned no content |
| `WARNING` | `[chatId] Guardrails violation in context streaming` | Violation detected mid-stream |
| `WARNING` | `[chatId] Cannot answer from context — falling back to RAG` | Neither phase could answer |

---

## Data Models

### `ContextDetectionResult` (Phase 1 output)

```python
class ContextDetectionResult(BaseModel):
    is_greeting: bool               # True if query is a greeting
    can_answer_from_context: bool   # True if query can be answered from last 10 turns
    reasoning: str                  # LLM's brief explanation
    answered_from_summary: bool     # Reserved; always False in current workflow
    context_snippet: Optional[str]  # Relevant excerpt for Phase 2 generation, or None
```

### `ContextDetectionSignature` (DSPy — Phase 1)

| Field | Type | Description |
|-------|------|-------------|
| `conversation_history` | Input | Last 10 turns formatted as JSON |
| `user_query` | Input | Current user query |
| `detection_result` | Output | JSON with `is_greeting`, `can_answer_from_context`, `reasoning`, `context_snippet` |

> Detection only — **no answer generated here**.

### `ContextResponseGenerationSignature` (DSPy — Phase 2)

| Field | Type | Description |
|-------|------|-------------|
| `context_snippet` | Input | Relevant excerpt from Phase 1 |
| `user_query` | Input | Current user query |
| `answer` | Output | Natural language response in the same language as the query |

---

## Decision Summary Table

| Scenario | Phase 1 LLM Calls | Phase 2 LLM Calls | Outcome |
|----------|--------------------|--------------------|---------|
| Greeting detected | 1 (`detect_context`) | 0 (static response) | Context responds (greeting) |
| Follow-up answerable from last 10 turns | 1 (`detect_context`) | 1 (`generate_context_response` or `stream_context_response`) | Context responds |
| Cannot answer from last 10 turns | 1 (`detect_context`) | 0 | Falls back to RAG |
| Phase 1 LLM error / JSON parse failure | — | 0 | Falls back to RAG |
| Phase 2 LLM error or empty answer | 1 | — | Falls back to RAG |

---

## File Reference

| File | Purpose |
|------|---------|
| `src/tool_classifier/context_analyzer.py` | Core LLM analysis logic (all three steps) |
| `src/tool_classifier/workflows/context_workflow.py` | Workflow executor (streaming + non-streaming) |
| `src/tool_classifier/classifier.py` | Classification layer that invokes context analysis |
| `src/tool_classifier/greeting_constants.py` | Static fallback greeting responses (ET/EN) |
| `tests/test_context_analyzer.py` | Unit tests for `ContextAnalyzer` |
| `tests/test_context_workflow.py` | Unit tests for `ContextWorkflowExecutor` |
| `tests/test_context_workflow_integration.py` | Integration tests for the full classify → route → execute chain |