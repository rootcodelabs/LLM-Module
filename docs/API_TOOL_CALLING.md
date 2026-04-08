# API Tool Calling — Architecture & Implementation



## Overview

API Tool Calling enables the LLM module to discover and invoke external API endpoints
in response to user queries. endpoints are
registered, semantically indexed in Qdrant, and retrieved at query time using hybrid search.

The feature has two halves:

| Half | What it does | Status |
|---|---|---|
| **Indexing pipeline** | Takes an endpoint definition → enriches it with LLM context → stores hybrid vectors in Qdrant |  Complete |
| **Tool classifier** | At query time, routes to the best matching endpoint via hybrid search |  In progress |

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
ToolClassifier  (src/tool_classifier/)
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

1. Validates required env vars (`endpoint_id`, `name`, `description`)
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