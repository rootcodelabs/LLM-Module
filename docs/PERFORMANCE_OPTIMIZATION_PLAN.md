# Vector Indexer — Performance Optimization Plan

**Date:** 2026-03-24  
**Scope:** `src/vector_indexer/`  
**Status:** Proposed

---

## TL;DR

The vector indexing pipeline is slow due to five root causes:

1. **Single-chunk context generation**: every chunk triggers an individual HTTP + LLM call to `/generate-context` with an artificial 0.1 s sleep between batches
2. **Small embedding batches**: batch size is 10 despite the `/embeddings` endpoint accepting up to 100
3. **Low concurrency caps**: only 3 documents and 5 chunks processed in parallel
4. **Verbose Qdrant logging**: 500+ `logger.info` lines emitted per upsert batch in the hot path
5. **Double file reads**: every file is read twice — once for SHA-256 hashing during discovery, and again during document loading

The recommended approach is a phased rollout: **config tuning → code-level fixes → architectural improvements**.

---

## Data Flow Overview

```
User triggers indexing
  ↓
main_indexer.py  process_all_documents()
  ├── DiffDetector  — identify new / modified / deleted files
  ├── DocumentLoader.discover_all_documents()  — glob scan + SHA-256 hash per file  [bottleneck 5]
  └── asyncio.Semaphore(3)  — process ≤3 documents concurrently  [bottleneck 3]
       ↓
       _process_single_document()
         ├── DocumentLoader.load_document()  — reads file again  [bottleneck 5]
         ├── ContextualProcessor.process_document()
         │     ├── _split_into_chunks()  (tiktoken)
         │     ├── api_client.generate_context_batch()  [bottleneck 1]
         │     │     └── POST /generate-context  ×1 per chunk  (Semaphore 5, batch 5, sleep 0.1s)
         │     └── _create_embeddings_in_batches()  [bottleneck 2]
         │           └── POST /embeddings  ×N  (batch 10, sleep 0.1s)
         └── QdrantManager.store_chunks()  [bottleneck 4]
               └── PUT /collections/{name}/points  (batch 100, per-point info logging)
```

---

## Phase 1 — Configuration Tuning (Quick Wins, No Logic Changes)

> Effort: minutes | Expected speedup: **2–5×**

### 1.1 Increase concurrency and batch sizes

File: `src/vector_indexer/config/vector_indexer_config.yaml`

| Setting | Current | Recommended | Reason |
|---------|---------|-------------|--------|
| `max_concurrent_documents` | `3` | `10` | API can handle more; semaphore limits safely |
| `max_concurrent_chunks_per_doc` | `5` | `15` | More parallel context generation calls per document |
| `embedding_batch_size` | `10` | `50` | `/embeddings` endpoint already accepts up to 100 |
| `context_batch_size` | `5` | `15` | More chunks dispatched per batch cycle |
| `batch_delay_seconds` | `0.1` | `0.0` | Artificial delay — no evidence of rate-limit necessity |
| `context_delay_seconds` | `0.05` | `0.0` | Same — re-add conditionally only if HTTP 429s appear |

### 1.2 Increase HTTP connection pool

File: `src/vector_indexer/api_client.py` — `httpx.Limits` in `__init__`

| Setting | Current | Recommended |
|---------|---------|-------------|
| `max_connections` | `10` | `50` |
| `max_keepalive_connections` | `5` | `20` |

---

## Phase 2 — Code-Level Fixes (Moderate Impact)

> Effort: hours | Expected speedup: **+1.5–3× on top of Phase 1**

All items in this phase are independent and can be implemented in parallel.

### 2.1 Remove verbose per-point logging from Qdrant upsert hot path

**File:** `src/vector_indexer/qdrant_manager.py`, `_store_chunks_in_collection()` (lines 173–185)

**Problem:** A `for idx, point in enumerate(batch)` loop logs each point's ID, vector length, vector sample, and payload keys at `logger.info`. For 100 points per batch this generates **500+ log lines per upsert call**. In production this both slows the event loop and floods log sinks.

**Fix:** Downgrade to `logger.debug` or remove the per-point loop entirely. Keep the summary `logger.info` line at the end.

```python
# BEFORE — inside _store_chunks_in_collection()
logger.info("=== QDRANT HTTP REQUEST PAYLOAD DEBUG ===")
logger.info(f"URL: {self.qdrant_url}/collections/{collection_name}/points")
logger.info("Method: PUT")
logger.info(f"Batch size: {len(batch)} points")
for idx, point in enumerate(batch):
    logger.info(f"Point {idx + 1}:")
    logger.info(f"  ID: {point['id']} (type: {type(point['id'])})")
    logger.info(f"  Vector length: {len(point['vector'])} ...")
    logger.info(f"  Vector sample: {point['vector'][:3]}...")
    logger.info(f"  Payload keys: {list(point['payload'].keys())}")
logger.info("=== END QDRANT REQUEST DEBUG ===")

# AFTER — replace with a single debug-level summary
logger.debug(
    f"Upserting batch {i // batch_size + 1} ({len(batch)} points) "
    f"to {collection_name}"
)
```

### 2.2 Remove artificial `asyncio.sleep()` delays

**Files:**
- `src/vector_indexer/api_client.py` line ~73 — `await asyncio.sleep(0.1)` between context batches
- `src/vector_indexer/contextual_processor.py` line ~277 — `await asyncio.sleep(delay)` between embedding batches

**Problem:** These delays were added to be "gentle on the API" but are not tied to any actual rate-limit response. For a document with 100 chunks, the delays alone add **10+ seconds of pure wait time**.

**Fix:** Remove both `asyncio.sleep()` calls. Add them back conditionally only when the API returns HTTP 429, using a response-driven back-off pattern.

### 2.3 Fix semaphore recreation inside the batch loop

**File:** `src/vector_indexer/api_client.py`, `generate_context_batch()`

**Problem:** `asyncio.Semaphore(self.config.max_concurrent_chunks_per_doc)` is created **inside** the `for i in range(...)` loop. Each batch of 5 chunks gets its own fresh semaphore, so only 5 chunks can run concurrently within that batch — but there is no limit across batches. Moving it outside the loop makes it a true global rate limiter, allowing overlap between batches and better concurrency.

```python
# BEFORE
for i in range(0, len(chunks), self.config.context_batch_size):
    batch = chunks[i : i + self.config.context_batch_size]
    semaphore = asyncio.Semaphore(self.config.max_concurrent_chunks_per_doc)  # ← recreated every iteration
    ...

# AFTER
semaphore = asyncio.Semaphore(self.config.max_concurrent_chunks_per_doc)  # ← created once
for i in range(0, len(chunks), self.config.context_batch_size):
    batch = chunks[i : i + self.config.context_batch_size]
    ...
```

### 2.4 Eliminate redundant file reads during document discovery

**File:** `src/vector_indexer/document_loader.py`, `discover_all_documents()`

**Problem:** Every file in the dataset is opened and fully read to compute a SHA-256 hash during discovery. The same file is then opened and read again inside `load_document()`. For a dataset with hundreds of documents this doubles I/O.

**Options (choose one):**

- **Option A (Recommended):** Defer hash computation into `load_document()`. Use the directory name as a temporary placeholder identifier during discovery, compute the real content hash once when the file is loaded.
- **Option B:** Cache `(path → content)` in a dict during discovery and pass it to `load_document()` to avoid re-reading.

### 2.5 Increase Qdrant upsert batch size and make it configurable

**File:** `src/vector_indexer/qdrant_manager.py` line 169, `src/vector_indexer/config/config_loader.py`

**Problem:** `batch_size = 100` is hardcoded. Qdrant handles batches of 500–1000 points well, reducing HTTP round-trips.

**Fix:** Increase to `500` and add `qdrant_batch_size: int = 500` to `VectorIndexerConfig` so it can be tuned in the YAML.

### 2.6 Parallelize discovery file hashing (if Option A in 2.4 is not chosen)

**File:** `src/vector_indexer/document_loader.py`, `discover_all_documents()`

If hash computation must remain in discovery, wrap each file read in `asyncio.to_thread()` with `concurrent.futures.ThreadPoolExecutor` to hash files in parallel instead of sequentially.

---

## Phase 3 — Architectural Improvements (High Impact, Higher Effort)

> Effort: days | Expected speedup: **+3–10× on top of Phase 2**

### 3.1 Add `/generate-context-batch` endpoint to LLM orchestration service *(blocks 3.2)*

**File:** `src/llm_orchestration_service_api.py`, `src/models/request_models.py`

**Problem:** `/generate-context` accepts a **single** `chunk_prompt`. Each chunk requires one HTTP round-trip plus one independent LLM inference call. For a document with 100 chunks, even with high concurrency you are serializing on LLM capacity. This is the **single largest bottleneck** in the entire pipeline.

**Fix:** Add a new endpoint:

```
POST /generate-context-batch
Request:  { document_prompt: str, chunk_prompts: List[str], ... }
Response: { contexts: List[str] }
```

Internally, the endpoint can either:
- submit all chunks as parallel LLM calls (same parallelism, fewer HTTP hops), or
- pack numbered chunks into a single LLM prompt and parse the list response (fewer LLM calls, higher risk of output parsing errors)

New request model needed in `src/models/request_models.py`:
```python
class BatchContextGenerationRequest(BaseModel):
    document_prompt: str
    chunk_prompts: List[str]
    environment: str
    connection_id: Optional[str] = None
    use_cache: bool = True
```

### 3.2 Update `api_client.py` to use the batch context endpoint *(depends on 3.1)*

**File:** `src/vector_indexer/api_client.py`

Replace the `for` loop of individual `_generate_context_with_retry()` calls in `generate_context_batch()` with a single `POST /generate-context-batch` call per document. Implement fallback to the single-chunk endpoint if the batch endpoint fails.

### 3.3 Implement producer/consumer pipeline parallelism *(parallel with 3.1)*

**File:** `src/vector_indexer/main_indexer.py`

**Problem:** Processing is strictly sequential per document: `chunk → context → embed → store`. While document N is being embedded, document N+1 sits idle waiting for the semaphore.

**Fix:** Use `asyncio.Queue` for a producer/consumer pattern:
- **Producer task**: discovers and chunks documents, puts `(doc_info, base_chunks)` onto a queue
- **Context task**: dequeues chunks, generates contexts, puts `(doc_info, contextual_chunks)` onto a second queue
- **Embed+Store task**: dequeues contextual chunks, generates embeddings, upserts to Qdrant

This overlaps all three phases across documents, maximising throughput.

### 3.4 Enable Qdrant gRPC transport *(parallel with 3.1–3.3)*

**File:** `src/vector_indexer/qdrant_manager.py`

Replace the raw `httpx.AsyncClient` REST implementation with the `qdrant-client` Python SDK using `prefer_grpc=True`. gRPC reduces per-call overhead by ~20–30% for bulk upserts due to binary framing vs. JSON serialization.

Note: `src/intent_data_enrichment/qdrant_manager.py` already has `prefer_grpc=False` — check for shared configuration before changing.

### 3.5 Reduce redundant document payload in context generation requests *(parallel with 3.1)*

**File:** `src/vector_indexer/api_client.py`, `src/llm_orchestration_service_api.py`

**Problem:** Every `/generate-context` call sends the **full document content** as `document_prompt`. For a 50 KB document with 50 chunks, this is **2.5 MB of repeated payload** per document — purely redundant network traffic.

**Options:**
- **Server-side document cache:** first call sends the document and receives a `document_id`; subsequent calls reference the `document_id` only
- **Verify Anthropic prompt caching:** `use_cache: True` is already set in the request — confirm via Langfuse traces that the Anthropic `cache_control` header is being sent and that cache hits are being recorded

---

## Verification Steps

After each phase:

1. **Benchmark** — index the same representative dataset (≥10 documents, ~50 chunks each) and compare wall-clock time before and after
2. **Regression tests** — `uv run pytest tests/ -v`
3. **Integration tests** — `uv run pytest tests/integration_tests/ -v --tb=short --log-cli-level=INFO`
4. **Monitor for 429s** — after removing delays and increasing concurrency, watch for rate-limit errors from LLM providers in Langfuse / Grafana Loki
5. **Chunk correctness** — spot-check that contextual content and Qdrant payloads are byte-for-byte identical to pre-optimization output
6. **Load test** — process a large dataset (100+ documents) to validate stability and memory behaviour under higher concurrency

---

## Decisions & Scope

| Decision | Rationale |
|----------|-----------|
| Phase 1 changes are immediately reversible | YAML values can be reverted in seconds |
| Batch delays removed without gate | No evidence they prevent errors; re-add on first observed 429 |
| Phase 3 items are separate PRs | Require API surface changes and architectural refactoring |
| Chunking strategy excluded | `chunk_size`, `chunk_overlap` affect retrieval quality — separate concern |
| Embedding model excluded | Provider selection is a quality / cost decision |

---

## Affected Files Summary

| File | Phase | Change |
|------|-------|--------|
| `src/vector_indexer/config/vector_indexer_config.yaml` | 1 | Concurrency & batch size values |
| `src/vector_indexer/api_client.py` | 1, 2 | Connection pool limits; semaphore placement; sleep removal |
| `src/vector_indexer/contextual_processor.py` | 2 | Remove embedding batch sleep |
| `src/vector_indexer/qdrant_manager.py` | 2, 3 | Remove debug logging; increase batch size; gRPC transport |
| `src/vector_indexer/document_loader.py` | 2 | Defer/parallelize file hashing |
| `src/vector_indexer/config/config_loader.py` | 2 | Add `qdrant_batch_size` to `VectorIndexerConfig` |
| `src/llm_orchestration_service_api.py` | 3 | New `/generate-context-batch` route |
| `src/models/request_models.py` | 3 | `BatchContextGenerationRequest` model |
| `src/vector_indexer/main_indexer.py` | 3 | Producer/consumer pipeline refactor |

---

## Expected Impact Summary

| Phase | Changes | Expected Speedup |
|-------|---------|-----------------|
| Phase 1 — Config | Concurrency, batch sizes, remove delays | **2–5×** |
| Phase 2 — Code | Logging, semaphore, hashing, Qdrant batch | **+1.5–3×** on top of Phase 1 |
| Phase 3 — Architecture | Batch context API, pipeline parallelism, gRPC | **+3–10×** on top of Phase 2 |
| **Combined** | All phases applied | **~10–50× overall** |
