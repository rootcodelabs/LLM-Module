# MCQ Flow Walkthrough — End-to-End Example

This document walks through the complete multi-step service (MCQ) flow using a concrete keyboard troubleshooting example, showing exactly how each implemented task contributes.

---

## Setup

A user wants to resolve a keyboard problem. The Ruuter DSL has:
- `Klaviatuuri_probleemi_lahendamine` — initial service (natural-language entry point)
- `Klaviatuuri_probleemi_lahendamine_mcq_1_0` — step 2: choose OS
- `Klaviatuuri_probleemi_lahendamine_mcq_2_0` — step 3: choose connection type → final answer

---

## Turn 1 — Natural Language (existing flow, unchanged)

**User types:** `"My keyboard is not working"`

```
Frontend → POST /orchestrate
{
  "chatId": "abc-123",
  "authorId": "user-456",
  "message": "My keyboard is not working",
  ...
}
```

**Pipeline:**

```
1. Pydantic sanitizer runs → message unchanged ✅ (Task 1 verified this)

2. process_orchestration_request() starts
   │
   ├─ STEP 0: Language detection → "en"
   │
   ├─ STEP 0.1: request.message.startswith(("#service,", "#common_service,"))
   │   → FALSE (it's natural language) → skip, continue normally
   │
   ├─ STEP 0.5: Query validation → valid
   ├─ Components init (LLM manager, guardrails)
   ├─ Input guardrails → allowed
   │
   ├─ ToolClassifier.classify() → SERVICE (confidence: 0.92)
   │
   ├─ route_to_workflow() → ServiceWorkflowExecutor.execute_async()
   │   ├─ Intent detection LLM → matched: "Klaviatuuri_probleemi_lahendamine"
   │   ├─ Entity extraction → {}
   │   ├─ _construct_service_endpoint()
   │   │   → "http://ruuter-public:8086/services/services/active/Klaviatuuri_probleemi_lahendamine"
   │   │
   │   ├─ _call_service_endpoint(url, "POST", [], "abc-123", "user-456")
   │   │   → Ruuter → DMapper returns:                    ← Task 3 parses ALL items
   │   │     [
   │   │       {"content": "Which operating system are you using?"},
   │   │       {"title": "Windows", "payload": "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0"},
   │   │       {"title": "Mac",     "payload": "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_1"}
   │   │     ]
   │   │
   │   │   Returns: {"content": "Which operating system...", "buttons": [{...}, {...}]}
   │   │
   │   ├─ Builds ChoiceButton objects                      ← Task 2 model
   │   └─ Returns OrchestrationResponse(
   │        content="Which operating system are you using?",
   │        buttons=[                                      ← Task 2 field
   │          ChoiceButton(title="Windows", payload="#service, /POST/.../mcq_1_0"),
   │          ChoiceButton(title="Mac",     payload="#service, /POST/.../mcq_1_1"),
   │        ]
   │      )
   │
   └─ Return to frontend
```

**Response JSON:**

```json
{
  "chatId": "abc-123",
  "llmServiceActive": true,
  "content": "Which operating system are you using?",
  "buttons": [
    {"title": "Windows", "payload": "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0"},
    {"title": "Mac",     "payload": "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_1"}
  ]
}
```

**Frontend renders:** "Which operating system are you using?" with buttons **[Windows] [Mac]**

---

## Turn 2 — Button Click (NEW short-circuit path)

**User clicks [Windows]** → the frontend sends the button's `payload` as the next message:

```
Frontend → POST /orchestrate
{
  "chatId": "abc-123",
  "message": "#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0",
  ...
}
```

**Pipeline:**

```
1. Pydantic sanitizer runs → "#service, /POST/..." unchanged ✅ (Task 1)

2. process_orchestration_request() starts
   │
   ├─ STEP 0: Language detection → "en" (cheap, still runs)
   │
   ├─ STEP 0.1: request.message.startswith(("#service,", "#common_service,"))
   │   → TRUE! ✅                                         ← Task 7
   │
   ├─ _get_service_workflow_executor()                     ← Task 7 helper
   │   → returns existing self.tool_classifier.service_workflow
   │
   ├─ executor.execute_direct_step(request, time_metric)   ← Task 6
   │   │
   │   ├─ _parse_service_prefix("#service, /POST/services/active/...mcq_1_0")  ← Task 5
   │   │   → ("POST", "http://ruuter-public:8086/services/services/active/Klaviatuuri_probleemi_lahendamine_mcq_1_0")
   │   │
   │   ├─ Log: "[abc-123] DIRECT STEP: http://ruuter-public:8086/services/..."
   │   │
   │   ├─ _call_service_endpoint(url, "POST", [], ...)    ← Task 3 (entities_array=[])
   │   │   → DMapper returns:
   │   │     [
   │   │       {"content": "What is the keyboard connection type?"},
   │   │       {"title": "USB",       "payload": "#service, /POST/.../mcq_2_0"},
   │   │       {"title": "Bluetooth", "payload": "#service, /POST/.../mcq_2_1"}
   │   │     ]
   │   │
   │   └─ Returns OrchestrationResponse(
   │        content="What is the keyboard connection type?",
   │        buttons=[ChoiceButton("USB", ...), ChoiceButton("Bluetooth", ...)]
   │      )
   │
   ├─ log_step_timings() → {language_detection: 0.002s, service.direct_step: 0.15s}
   └─ Return immediately
```

**What was SKIPPED** (the whole point of the short-circuit):

| Skipped step | Why it matters |
|---|---|
| ~~Query validation~~ | Would flag `#service` as gibberish/malformed |
| ~~Component initialization~~ | Expensive (LLM manager, retriever, Vault secrets) |
| ~~Input guardrails~~ | Would reject a machine-generated payload string |
| ~~ToolClassifier.classify()~~ | LLM call — costs money and time |
| ~~Intent detection LLM~~ | Another LLM call — meaningless for a pre-formed URL |
| ~~Entity extraction~~ | No natural language entities to extract |
| ~~Semantic search (Qdrant)~~ | No need to find a service — URL is already known |

---

## Turn 3 — Final Step (no more buttons)

**User clicks [USB]** → message = `"#service, /POST/services/active/Klaviatuuri_probleemi_lahendamine_mcq_2_0"`

Same short-circuit path. DMapper returns only one item (no buttons):

```json
[
  {"content": "Try unplugging the USB keyboard, wait 10 seconds, and plug it back in. If that doesn't work, try a different USB port."}
]
```

No items after index 0 → `buttons = []` → `buttons_list` is empty → `buttons=None` in the response.

**Response:**

```json
{
  "chatId": "abc-123",
  "content": "Try unplugging the USB keyboard, wait 10 seconds, and plug it back in. If that doesn't work, try a different USB port.",
  "buttons": null
}
```

Frontend renders the answer text. No buttons → the flow is complete.

---

## Streaming Variant (`/orchestrate/stream`)

The same flow works via the streaming endpoint. When the `#service` prefix is detected by Task 8, `execute_direct_step_streaming()` is called and yields exactly 2 SSE messages:

```
data: {"chatId":"abc-123","payload":{"content":"What is the keyboard connection type?","buttons":[{"title":"USB","payload":"#service, /POST/..."},{"title":"Bluetooth","payload":"#service, /POST/..."}]},"timestamp":"...","sentTo":[]}

data: {"chatId":"abc-123","payload":{"content":"END"},"timestamp":"...","sentTo":[]}
```

The `buttons` key inside the SSE `payload` is enabled by Task 4's extension to `format_sse()`.

---

## Task-by-Task Recap

| Task | Where it fires | What it does |
|------|---------------|--------------|
| **1** | Pydantic model validator (HTTP parse time) | Verified `#service, /POST/...` passes through `sanitize_message()` unchanged |
| **2** | `OrchestrationResponse` / `TestOrchestrationResponse` models | Added `buttons: Optional[List[ChoiceButton]]` field |
| **3** | `_call_service_endpoint()` | Returns `{"content": ..., "buttons": [...]}` instead of just the first string |
| **4** | `format_sse()` | SSE payload includes `"buttons"` key when buttons are present (streaming path) |
| **5** | `_parse_service_prefix()` | Parses `"#service, /POST/..."` → `("POST", "http://ruuter-public:8086/...")` |
| **6** | `execute_direct_step()` / `execute_direct_step_streaming()` | Parse → call endpoint → wrap response. No LLM, no discovery, no entity extraction |
| **7** | `process_orchestration_request()` | `startswith` check → short-circuit to Task 6 (non-streaming `/orchestrate`) |
| **8** | `stream_orchestration_response()` | `startswith` check → short-circuit to Task 6 (streaming `/orchestrate/stream`) |
| **9** | `/orchestrate/test` handler | `buttons=response.buttons` forwarded in the `TestOrchestrationResponse` copy block |
