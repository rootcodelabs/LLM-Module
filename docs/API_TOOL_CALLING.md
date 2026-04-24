# API Tool Calling — Architecture & Implementation



## Overview

API Tool Calling enables the LLM module to discover and invoke external API endpoints
in response to user queries. Endpoints are registered, semantically indexed in Qdrant,
and retrieved at query time using hybrid search. Once matched, a multi-turn agentic
loop collects all required parameters from the user before the API call is made.


| Component | What it does | Status |
|---|---|---|
| **Indexing pipeline** | Takes an endpoint definition → enriches it with LLM context → stores hybrid vectors in Qdrant | ✅ Complete |
| **Tool classifier** | At query time, routes to the best matching endpoint via hybrid search + LLM disambiguation | ✅ Complete |
| **Agentic loop** | Multi-turn parameter collection with session persistence, language-aware clarifying questions, param correction, continuation prompt, and intent-switch detection | ✅ Complete |
| **API caller** | Execute the collected params against the real API endpoint and format the response | 🔧 Planned (next task) |

---

## System Components

```
Ruuter DSL  (/api-tools/index)
        ↓  HTTP POST
CronManager  (api_tool_indexer job)
        ↓  exec
api_tool_indexer.sh  (bash)
        ↓  python3
main_indexer.py  (indexing pipeline)
        ↓  upsert
api_tool_collection  (Qdrant)
        ↑  query at runtime
APISemanticSearcher  (src/tool_classifier/api_semantic_searcher.py)
        ↑  called by
ToolClassifier._try_api_tool_classification()
        ↓  ClassificationResult(workflow=API_TOOL_CALLING)
APIToolWorkflowExecutor  (src/tool_classifier/workflows/api_tool_workflow.py)
        ↓  multi-turn param collection
AgenticLoop  (src/tool_classifier/agentic_loop.py)
        ↓  session state
APIToolSessionStore  (Redis, keyed by chat_id, 30-min TTL)
```

---

## Part 1 — Indexing Pipeline

### Trigger: `POST /rag-search/api-tools/index`

Defined in [DSL/Ruuter.public/rag-search/POST/api-tools/index.yml](../DSL/Ruuter.public/rag-search/POST/api-tools/index.yml).

**Request body** (sent from Postman while no UI exists):

```json
{
  "endpointId": "a3f7c2d1-84e6-4b19-92f3-d51c7e890ab2",
  "serviceId": "",
  "name": "get_national_holidays",
  "description": "Fetch national holidays for a specific country to see when they have public days off.",
  "method": "GET",
  "url": "https://openholidaysapi.org/PublicHolidays",
  "visibility": "public",
  "type": "custom_endpoint",
  "params": [
    {"name": "countryIsoCode", "type": "string", "required": true,  "description": "The 2-letter ISO country code (e.g., EE for Estonia, DE for Germany)"},
    {"name": "languageIsoCode", "type": "string", "required": false, "description": "The 2-letter ISO language code (e.g., ET, EN)"},
    {"name": "validFrom",       "type": "date",   "required": false, "description": "Start date for the holiday search (YYYY-MM-DD)"},
    {"name": "validTo",         "type": "date",   "required": false, "description": "End date for the holiday search (YYYY-MM-DD)"}
  ]
}
```

Ruuter URL-encodes `params` (JSON array → `encodeURIComponent`) and forwards everything to
CronManager via:

```
POST http://cron-manager:8080/execute/api_tool_indexer/index_endpoint
     ?endpoint_id=...&name=...&params=%5B...%5D
```

---

### CronManager Job: `api_tool_indexer`

Defined in [DSL/CronManager/DSL/api_tool_indexer.yml](../DSL/CronManager/DSL/api_tool_indexer.yml).

```yaml
index_endpoint:
  trigger: off         # Not scheduled — on-demand only
  type: exec
  command: "/app/scripts/api_tool_indexer.sh"
  allowedEnvs: ['endpoint_id', 'service_id', 'name', 'description',
                 'method', 'url', 'visibility', 'type', 'params']
```

`trigger: off` means this job is never run on a schedule — it only executes when
CronManager receives an HTTP `POST /execute/api_tool_indexer/index_endpoint` call.
The query params from Ruuter are injected as environment variables for the shell script.

---

### Shell Script: `api_tool_indexer.sh`

Defined in [DSL/CronManager/script/api_tool_indexer.sh](../DSL/CronManager/script/api_tool_indexer.sh).

**What it does (in order):**

1. Validates required env vars (`endpoint_id`, `name`, `description`, `url`)
2. Activates the pre-built Python venv at `/app/python_virtual_env`
3. Installs required packages via `uv pip install` (`httpx`, `pydantic`, `qdrant-client`, `loguru`)
4. Sets `PYTHONPATH` to include `/app/src`
5. URL-decodes the `params` env var back to a JSON array and writes it to a temp file
6. Invokes `main_indexer.py` with CLI args (avoids shell parsing issues with JSON)
7. Cleans up the temp file; exits with the Python exit code



---

### Python Indexing Pipeline: `main_indexer.py`

Defined in [src/api_tool_indexer/main_indexer.py](../src/api_tool_indexer/main_indexer.py).

**Entry point**: `index_endpoint(endpoint_data: EndpointData) → IndexingResult`

The pipeline runs 5 sequential steps:

#### Step 1 — LLM Context Generation

Builds a structured prompt from the endpoint's name, description, method, URL, and
params, then calls the internal `/generate-context` endpoint via `LLMAPIClient`.

The `CONTEXT_TEMPLATE` (in `constants.py`) instructs the LLM to generate a rich
semantic description covering:
- What the user wants to accomplish by calling this endpoint
- Key terms and synonyms
- Related concepts and use cases
- Common natural language phrasings
- Response is in the **same language as the description** (Estonian / English / Russian)

**`embed_text`** is then assembled as:

```
{name}. {description}. {enriched_context}. Parameters: {params_summary}
```

where `params_summary` is a semicolon-separated one-liner like:
```
countryIsoCode (string, required): ISO country code; validFrom (date, optional): Start date
```

#### Step 2 — Dense Embedding

`embed_text` is sent to Azure OpenAI `text-embedding-3-large` via `LLMAPIClient.create_embedding()`.
Returns a **3072-dimensional float vector** (cosine similarity space).

#### Step 3 — Sparse (BM25) Vector

`embed_text` is tokenised and hashed using `compute_sparse_vector()` from
[src/tool_classifier/sparse_encoder.py](../src/tool_classifier/sparse_encoder.py)
(shared with the tool classifier).

```
tokens = regex word-split of lowercase embed_text
index  = MD5(token)[:4 bytes] % 50_000  (hash to vocab space)
value  = term frequency (collisions are accumulated)
```

Returns `SparseVector(indices=[...], values=[...])` — sorted for consistency.

#### Step 4 — Delete Existing Qdrant Point (idempotent)

`ApiToolQdrantManager.delete_endpoint_point(endpoint_id)` filters by `endpoint_id`
field in the payload and deletes the point before upserting. This ensures re-indexing
the same endpoint never creates duplicates.

#### Step 5 — Upsert to Qdrant

A `PointStruct` is built:

```python
PointStruct(
    id      = endpoint_id,            # UUID used directly as Qdrant point ID
    vector  = {
        "dense":  [v1, v2, ..., v3072],
        "sparse": {"indices": [...], "values": [...]},
    },
    payload = {                        # Stored metadata — no extra DB lookup needed
        "endpoint_id":      "...",
        "name":             "get_national_holidays",
        "description":      "...",
        "url":              "https://openholidaysapi.org/PublicHolidays",
        "method":           "GET",
        "params":           [...],
        "enriched_context": "...",
        "service_id":       "...",
    }
)
```

Upserted into the `api_tool_collection` Qdrant collection.

---

### Qdrant Collection: `api_tool_collection`

Created automatically on first run by `ApiToolQdrantManager.ensure_collection()`.

```
Collection:  api_tool_collection
Vectors:
  "dense"  → VectorParams(size=3072, distance=COSINE)
  "sparse" → SparseVectorParams(index=SparseIndexParams(on_disk=False))
```

One point per endpoint. The full `EnrichedEndpoint` payload is stored so the agentic
loop can execute the API call without an additional database round-trip.

---

### Data Models

**`EndpointData`** — input to the pipeline (from Postman / DB):

| Field | Type | Required | Description |
|---|---|---|---|
| `endpoint_id` | UUID |  | Unique identifier |
| `name` | str |  | snake_case function name |
| `description` | str |  | Human-readable purpose |
| `url` | str |  | Full target API URL |
| `method` | str |  | `GET` or `POST` |
| `params` | List[Dict] | | Parameter schema `[{name, type, required, description}]` |
| `service_id` | UUID | | Parent service group |
| `visibility` | str | | `public` or `private` (default: `public`) |
| `type` | str | | Endpoint type (default: `custom_endpoint`) |

**`ParamSchema`** — schema for each param:

| Field | Type | Description |
|---|---|---|
| `name` | str | Parameter name |
| `type` | str | `string`, `date`, `integer`, `boolean`, `number` |
| `required` | bool | Whether the caller must supply this param |
| `description` | str | Human-readable description |

---


## Part 2 — Tool Classifier (Query-Time)

### Overview

At query time, `ToolClassifier` in [src/tool_classifier/classifier.py](../src/tool_classifier/classifier.py) the layer by layer execution happens 


1. **Service search** → `intent_collections` (Qdrant) — existing Bürokratt services
2. **API Tool search** → `api_tool_collection` (Qdrant) — registered API tool endpoints

API tool search (`_try_api_tool_classification`) is triggered when:
- `SERVICE_WORKFLOW_ENABLED=false` (service workflow disabled globally)
- Dense service search returns no results
- Service cosine score falls below `DENSE_MIN_THRESHOLD`

It is **always** tried before falling back to Context/RAG.

---

### Component: `APISemanticSearcher`

Defined in [src/tool_classifier/api_semantic_searcher.py](../src/tool_classifier/api_semantic_searcher.py).

Instantiated once in `ToolClassifier.__init__()` and reuses the shared Qdrant `httpx.AsyncClient`.

**Constructor:**

```python
APISemanticSearcher(
    embedding_service=orchestration_service,   # generates dense embeddings
    qdrant_client=self._qdrant_client,         # shared connection pool
    disambiguator=None,                        # optional: inject for testing
)
```

**Key constants** (from `constants.py`):

| Constant | Value | Purpose |
|---|---|---|
| `API_TOOL_COLLECTION` | `api_tool_collection` | Qdrant collection name |
| `API_TOOL_SEARCH_TOP_K` | `5` | Max hybrid results |
| `API_TOOL_MIN_THRESHOLD` | cosine threshold | Below this → no match |
| `API_TOOL_HIGH_CONFIDENCE_THRESHOLD` | cosine threshold | Above this → high confidence |
| `API_TOOL_SCORE_GAP_THRESHOLD` | gap threshold | Minimum lead over runner-up |

---

### Search Flow: `APISemanticSearcher.search()`

```
User query
    │
    ├─ precomputed_embedding provided? → reuse it (no extra API call)
    └─ otherwise → generate dense embedding via embedding_service
    │
    ▼
Step 1: Dense search (api_tool_collection)
    → Real cosine similarity scores per endpoint
    │
    ├─ No results → return []
    ├─ top_cosine < API_TOOL_MIN_THRESHOLD → return []
    └─ continue
    │
    ▼
Step 2: Hybrid search (dense + sparse/BM25 + RRF)
    → Best-ranked results by RRF fusion score
    │  Falls back to dense results if hybrid returns nothing
    │
    ▼
Step 3: Annotate confidence for each hybrid result
    │
    │  cosine lookup: dense_cosine_map[endpoint_id]
    │             └─ fallback: point["cosine_score"] (sparse-driven result)
    │             └─ skip if neither available
    │
    │  effective_gap = this_cosine − best_other_cosine_in_dense
    │
    ├─ i==0 AND cosine ≥ HIGH_THRESHOLD AND effective_gap ≥ GAP_THRESHOLD → "high"
    ├─ cosine ≥ MIN_THRESHOLD → "medium"
    └─ else → skip
    │
    ▼
Step 4: Resolve to exactly one result
    ├─ high-confidence result exists → return immediately
    ├─ single medium + large gap → return directly
    └─ multiple medium OR small gap → LLM disambiguation
           │
           └─ EndpointDisambiguatorModule (DSPy + asyncio.to_thread)
                  → picks winner or returns None
                  → None means no match → return []
```

---

### Embedding Reuse

When `ToolClassifier.classify()` already generated a dense embedding for the service
search, it passes it as `precomputed_embedding` to `_try_api_tool_classification`:

```python
api_tool_result = await self._try_api_tool_classification(
    query, request, precomputed_embedding=query_embedding
)
```

`APISemanticSearcher.search()` skips the embedding step entirely when this is provided,
saving one embedding API call per request.

---

### LLM Disambiguation: `EndpointDisambiguatorModule`

Used when multiple medium-confidence endpoints score similarly and no clear winner
can be determined from cosine scores alone.

- DSPy `Predict` module with `EndpointDisambiguationSignature`
- Inputs: `user_query` + `candidates` (JSON list of `{endpoint_id, name, description, cosine_score}`)
- Output: `best_endpoint_id` — the winning `endpoint_id`, or `"none"` if no match
- Run via `asyncio.to_thread()` to avoid blocking the async event loop
- Understands Estonian, Russian, and English queries

---

### Feature Flag

API tool calling is gated by `FeatureFlags.API_TOOL_CALLING_WORKFLOW_ENABLED`.
When `false`, `_try_api_tool_classification` returns `None` immediately without
touching Qdrant.

---

### Component: `APIToolWorkflowExecutor`

Defined in [src/tool_classifier/workflows/api_tool_workflow.py](../src/tool_classifier/workflows/api_tool_workflow.py).

Handles `WorkflowType.API_TOOL_CALLING` after `ToolClassifier.classify()` has set
`matched_endpoint` in the context dict.

**Responsibilities:**

- **Turn 1 (new session):** reads `context["matched_endpoint"]`, creates a new
  `APIToolSession` in Redis, runs the first agentic loop turn.
- **Turn 2-N (resume):** loads the existing session from Redis, runs the next turn.
- **Fast path:** if the endpoint has no required params, immediately returns the
  completed JSON without starting a session.
- **Completion:** when all params are collected, deletes the session and returns a
  JSON response with `status=params_collected`.
- **Max turns:** deletes the session and returns `None` to trigger RAG fallback.
- **Streaming:** wraps the short clarifying-question response in a single SSE frame
  + `END` marker.

**Completed response format:**

```json
{
  "status": "params_collected",
  "endpoint": { "name": "get_public_holidays" },
  "collected_params": {
    "countryIsoCode": "EE",
    "validFrom": "2026-01-01",
    "validTo": "2026-12-31"
  }
}
```

The actual API call and response formatting are handled by the next planned task.

---

## Part 3 — Agentic Loop (Multi-Turn Parameter Collection)

### Overview

Defined in [src/tool_classifier/agentic_loop.py](../src/tool_classifier/agentic_loop.py).

`AgenticLoop` is **stateless** — it carries no internal state between HTTP requests.
All state is passed in as arguments (loaded from Redis by the workflow executor before
calling `run_turn`) and saved back to Redis inside `run_turn` before returning.

### Session Model: `APIToolSession`

Defined in [src/models/session_models.py](../src/models/session_models.py).

Stored in Redis keyed by `chat_id` with a **30-minute sliding TTL**.

| Field | Type | Description |
|---|---|---|
| `chat_id` | str | Unique conversation identifier |
| `state` | str | Current state (`collecting_params`, etc.) |
| `selected_endpoint` | dict | Full endpoint payload from Qdrant |
| `collected_params` | dict | Parameters collected so far |
| `turn_count` | int | Number of turns elapsed |
| `max_turns` | int | Max turns before fallback (default: 5) |
| `awaiting_continuation` | bool | True when continuation prompt has been shown |
| `detected_language` | str | Language from first message (`en`, `et`, `ru`) — persisted so all clarifying questions use the same language |

### Turn Flow

```
APIToolWorkflowExecutor._run()
    │
    ├─ Load session from Redis (or create new)
    │
    └─ AgenticLoop.run_turn(
           user_message, conversation_history,
           params_schema, collected_params,
           turn_count, max_turns, awaiting_continuation,
           session_language
       )
           │
           ├─ AWAITING_CONTINUATION_DECISION?
           │     yes → parse yes/no from user_message
           │             yes → clear flag, continue collecting
           │             no  → return MAX_TURNS_REACHED (RAG fallback)
           │
           ├─ ParamExtractionModule.forward()
           │     → DSPy extracts params from user_message + conversation_history
           │     → uses session_language for all questions
           │     → new values OVERWRITE old (allows corrections)
           │
           ├─ All required params present? → COMPLETED
           │
           ├─ turn_count reached CONTINUATION_TURN (default: 3)?
           │     → set awaiting_continuation=True
           │     → return AWAITING_CONTINUATION_DECISION
           │     → question = localized CONTINUATION_QUESTION (EN/ET/RU)
           │
           └─ else → generate clarifying question for next missing param
                   → return NEEDS_INPUT
           │
           └─ Save updated session to Redis
```

### Key Behaviours

**Language persistence:**
The language is detected once from the user's first message and stored in
`APIToolSession.detected_language`. All subsequent clarifying questions and the
continuation prompt are generated in that language, even when follow-up replies
like "yes" or "2026-01-01" are too short to re-detect reliably.

Supported: `en` (default), `et` (Estonian), `ru` (Russian).

**Parameter correction:**
If the user says "No, use Russia instead of Estonia", the extractor overwrites the
previously collected `countryIsoCode` value. There is no guard preventing
re-extraction of already-collected params — new values always win.

**Continuation prompt:**
After `CONTINUATION_TURN` turns without completing, the loop asks the user whether
to continue. If the user says no (or anything not in the yes-list), the session is
abandoned and the request falls back to the RAG workflow.

Localized continuation questions are defined in
[src/tool_classifier/constants.py](../src/tool_classifier/constants.py):
`CONTINUATION_QUESTION`, `CONTINUATION_QUESTION_ET`, `CONTINUATION_QUESTION_RU`.

**History isolation:**
On turn 0 (first turn of a new session), `conversation_history=[]` is passed to the
extractor regardless of what the API sends. This prevents parameter values from a
previous completed session from being re-used for the new request.

**Constants** (in `src/tool_classifier/constants.py`):

| Constant | Value | Description |
|---|---|---|
| `CONTINUATION_TURN` | `3` | Turn at which the continuation prompt is shown |

---

## Part 4 — Session Management & Intent Switch Detection

### `APIToolSessionStore`

Defined in [src/utils/api_tool_session_store.py](../src/utils/api_tool_session_store.py).

Redis-backed store. Key format: `session:{chat_id}`. TTL resets on every `update()`.

Operations: `save()`, `get()`, `update()`, `delete()`.

### Session Lifecycle

```
Turn 1: new query matches API tool endpoint
    → session CREATED (state=collecting_params)
    → clarifying question returned

Turn 2-N: user replies
    → session LOADED → loop runs → session UPDATED

Final turn: all params collected
    → session DELETED
    → completed JSON returned

OR: max turns reached / user says "no" to continuation
    → session DELETED
    → None returned → RAG fallback
```

### Intent Switch Detection

Defined in `ToolClassifier.classify()` — the session-resume short-circuit block.

Before resuming an active session, the classifier runs `_try_api_tool_classification()`
on the new message. If it matches a **different** endpoint with sufficient confidence,
the old session is abandoned and the new query starts fresh:

```python
new_api_match = await self._try_api_tool_classification(query, request)
if (
    new_api_match is not None
    and new_api_match.metadata["matched_endpoint"]["name"] != endpoint_name
):
    await session_store.delete(request.chatId)
    return new_api_match  # start new session for different endpoint
```

### Test Endpoint Behaviour (`/orchestrate/test`)

The test endpoint hardcodes `chatId="test-session"` for all requests. Because every
test user shares this ID, any incomplete session would be resumed by the next
unrelated test query.

**Fix:** the test endpoint deletes `"test-session"` from Redis at the **start** of
every request, before classification runs. This makes each test query a fresh
single-turn request.

**Trade-off:** multi-turn API tool flows cannot be tested via the test-LLM page.
The session is wiped before turn 2 can use it. To test multi-turn flows, use the
production `/orchestrate/stream` endpoint (which uses unique `chatId` per tab) or
the integration test script.

---

### End-to-End Flow (Query Time)

```
Turn 1 — User: "What are the public holidays in Estonia?"
    │
    ▼
ToolClassifier.classify()
    │
    ├─ No active session in Redis for this chat_id
    ├─ Dense search (intent_collections) → low cosine → below threshold
    └─ _try_api_tool_classification()
           └─ APISemanticSearcher.search()
                  ├─ Dense: get_public_holidays cosine=0.87 → high confidence
                  └─ return [APIToolSearchResult(name="get_public_holidays", ...)]
           └─ ClassificationResult(workflow=API_TOOL_CALLING, metadata={matched_endpoint: {...}})
    │
    ▼
APIToolWorkflowExecutor._run()
    ├─ No existing session → create new APIToolSession (turn_count=0, language=en)
    └─ AgenticLoop.run_turn(turn_count=0, history=[])
           ├─ ParamExtractionModule: no params in "What are the public holidays in Estonia?"
           │   but countryIsoCode=EE can be inferred → extracted
           ├─ Missing: validFrom, validTo
           └─ NEEDS_INPUT → "Which date range would you like? (validFrom, validTo)"
    │
    Session saved to Redis
    ▼
Bot: "Which date range would you like? Please provide validFrom and validTo (YYYY-MM-DD)."

---

Turn 2 — User: "This year, 2026-01-01 to 2026-12-31"
    │
    ▼
ToolClassifier.classify()
    ├─ Active session found for chat_id → run intent-switch check
    ├─ _try_api_tool_classification("This year, 2026-01-01 to 2026-12-31")
    │   → cosine=0.12 < threshold → no new API tool match
    └─ Same endpoint → resume session → ClassificationResult(reason=active_session_resume)
    │
    ▼
APIToolWorkflowExecutor._run()
    └─ AgenticLoop.run_turn(turn_count=1, collected_params={countryIsoCode: "EE"})
           ├─ ParamExtractionModule: extracts validFrom=2026-01-01, validTo=2026-12-31
           ├─ All required params present
           └─ COMPLETED
    │
    Session DELETED from Redis
    ▼
Bot: {"status": "params_collected", "endpoint": {"name": "get_public_holidays"}, "collected_params": {"countryIsoCode": "EE", "validFrom": "2026-01-01", "validTo": "2026-12-31"}}
```

---

## Part 5 — Integration Testing

### Test Script

Defined in [tests/api_tool_eval/integration_test_agentic_loop.py](../tests/api_tool_eval/integration_test_agentic_loop.py).

Runs end-to-end against the live service at `http://localhost:8100` via `/orchestrate`.
Each scenario uses a unique `chatId` (UUID) so sessions are fully isolated.

```bash
uv run --no-project --with requests python tests/api_tool_eval/integration_test_agentic_loop.py \
  --no-fail-fast \
  --output tests/api_tool_eval/integration-results.json
```

### Covered Scenarios

| # | Scenario | Turns | What it validates |
|---|---|---|---|
| 1 | Single-turn complete | 1 | Vehicle tax with plate number in first message → immediate completion |
| 2 | Multi-turn EN | 2 | Public holidays, country extracted turn 1, dates provided turn 2 |
| 3 | Multi-turn ET | 2 | School holidays in Estonian → language-aware classification |
| 4 | No-params fast path | 1 | Parliament votings endpoint has no required params → instant completion |
| 5 | Address search | 2 | Two-turn address lookup |
| 6 | Electricity prices | 2 | Datetime params across two turns |
| 7 | Session isolation | 2 | Two different chat IDs — no param leak between sessions |
| 8 | AWAITING_CONTINUATION → yes | 4+ | User says "yes" at continuation prompt → loop resumes |
| 9 | MAX_TURNS_REACHED | 5+ | User never provides params → falls back to RAG |