# Service Data Enrichment Pipeline - Specification

**Version**: 1.0  
**Date**: February 19, 2026  
**Status**: Specification  

---

## 1. Overview

### 1.1 Purpose

This specification defines the **Service Data Enrichment Pipeline** - a system that automatically enriches service metadata and indexes it in Qdrant for intent classification in the Tool Classifier workflow.

### 1.2 Goals

- **Enrich service data** with LLM-generated context (synonyms, related terms, alternate phrasings)
- **Index enriched data** in Qdrant's `intent_collection` for semantic search
- **Maintain synchronization** between PostgreSQL services table and Qdrant
- **Provide API endpoint** for manual triggering of enrichment

### 1.3 Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Service Creation (External System)                          │
│     - Admin UI / Management API                                 │
│     - Inserts service record into PostgreSQL services table     │
│     - Calls enrichment endpoint WITH service data               │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Enrichment API Call                                         │
│     POST /rag-search/services/enrich                            │
│     Body: { service_id, name, description, examples, ... }      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Ruuter Endpoint (DSL)                                       │
│     - Validates request payload                                 │
│     - Calls CronManager with service data                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. CronManager Execution                                       │
│     - Executes: script/service_enrichment.sh                    │
│     - Environment: service_id, service_data (JSON)              │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Python Enrichment Script                                    │
│     src/service_enrichment/enrich_and_index.py                  │
│     - Parse service data                                        │
│     - Call LLM to generate enriched context                     │
│     - Construct embedding text                                  │
│     - Generate vector embedding (OpenAI text-embedding-3-large) │
│     - Upsert document into Qdrant intent_collection             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. Response                                                    │
│     - Success: { success: true, service_id: "...", ... }        │
│     - Error: { success: false, error: "...", ... }              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger Mechanism | **Manual API call** | Clean separation, explicit control, easier debugging |
| Enrichment Strategy | **LLM-based expansion** | Generates high-quality synonyms and variations |
| Execution Mode | **Synchronous** | Guarantees service is indexed before returning |
| Qdrant Operation | **Upsert** | Idempotent, handles updates gracefully |
| Error Handling | **Graceful fallback** | Store original data if enrichment fails |

---

## 2. Components

### 2.1 Database Schema (Already Exists)

**Table**: `public.services`

```sql
CREATE TABLE public.services (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  service_id TEXT NOT NULL UNIQUE, 
  ruuter_type ruuter_request_type DEFAULT 'GET',
  current_state service_state DEFAULT 'draft',
  is_common BOOLEAN NOT NULL DEFAULT FALSE,
  slot TEXT NOT NULL DEFAULT '',
  entities text[] NOT NULL DEFAULT '{}',
  examples text[] NOT NULL DEFAULT '{}',
  structure JSON NOT NULL DEFAULT '{}',
  endpoints JSON NOT NULL DEFAULT '[]',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Note**: The enrichment endpoint receives service data directly from the caller, so no Resql query is needed.

### 2.2 Ruuter Endpoint (NEW)

**File**: `DSL/Ruuter.public/rag-search/POST/services/enrich.yml`

```yaml
declaration:
  call: declare
  version: 0.1
  description: "Enrich service data and index in Qdrant"
  method: post
  accepts: json
  returns: json
  namespace: rag-search
  allowlist:
    body:
      - field: service_id
        type: string
        description: "Unique service identifier"
        required: true
      - field: name
        type: string
        description: "Service name"
        required: true
      - field: description
        type: string
        description: "Service description"
        required: true
      - field: examples
        type: array
        description: "Example queries"
        required: false
      - field: entities
        type: array
        description: "Expected entity names"
        required: false
      - field: ruuter_type
        type: string
        description: "HTTP method (GET/POST)"
        required: false
      - field: current_state
        type: string
        description: "Service state (active/inactive/draft)"
        required: false
      - field: is_common
        type: boolean
        description: "Is common service"
        required: false

validate_request:
  assign:
    service_id: ${incoming.body.service_id}
    service_name: ${incoming.body.name}
    service_description: ${incoming.body.description}
  next: check_required_fields

check_required_fields:
  switch:
    - condition: ${!service_id || service_id.trim() === ''}
      next: return_missing_service_id
    - condition: ${!service_name || service_name.trim() === ''}
      next: return_missing_name
    - condition: ${!service_description || service_description.trim() === ''}
      next: return_missing_description
    - condition: true
      next: prepare_service_data

return_missing_service_id:
  status: 400
  return:
    success: false
    error: "MISSING_SERVICE_ID"
    message: "service_id is required"
  next: end

return_missing_name:
  status: 400
  return:
    success: false
    error: "MISSING_NAME"
    message: "name is required"
  next: end

return_missing_description:
  status: 400
  return:
    success: false
    error: "MISSING_DESCRIPTION"
    message: "description is required"
  next: end

prepare_service_data:
  assign:
    service_data:
      service_id: ${service_id}
      name: ${service_name}
      description: ${service_description}
      examples: ${incoming.body.examples || []}
      entities: ${incoming.body.entities || []}
      ruuter_type: ${incoming.body.ruuter_type || 'GET'}
      current_state: ${incoming.body.current_state || 'draft'}
      is_common: ${incoming.body.is_common || false}
    service_json: ${JSON.stringify(service_data)}
  log: "Enriching service: ${service_id}"
  next: execute_enrichment

execute_enrichment:
  call: http.post
  args:
    url: "[#RAG_SEARCH_CRON_MANAGER]/execute/service_enrichment/enrich_and_index"
    query:
      service_id: ${service_id}
      service_data: ${service_json}
  result: enrichment_result
  next: check_enrichment_success

check_enrichment_success:
  switch:
    - condition: ${enrichment_result.response.status >= 200 && enrichment_result.response.status < 300}
      next: return_success
    - condition: true
      next: return_enrichment_error

return_success:
  status: 200
  return:
    success: true
    service_id: ${service_id}
    message: "Service enriched and indexed successfully"
    enrichment_details: ${enrichment_result.response.body}
  next: end

return_enrichment_error:
  status: 500
  return:
    success: false
    error: "ENRICHMENT_FAILED"
    message: "Failed to enrich and index service"
    details: ${enrichment_result.response.body || enrichment_result.error}
  next: end
```

### 2.3 CronManager DSL (NEW)

**File**: `DSL/CronManager/DSL/service_enrichment.yml`

```yaml
enrich_and_index:
  trigger: off
  type: exec
  command: "../app/scripts/service_enrichment.sh"
  allowedEnvs: ['service_id', 'service_data']
```

### 2.4 Shell Script (NEW)

**File**: `DSL/CronManager/script/service_enrichment.sh`

```bash
#!/bin/bash

echo "[SERVICE_ENRICHMENT] Starting service enrichment pipeline..."

# Validate required environment variables
if [ -z "$service_id" ] || [ -z "$service_data" ]; then
  echo "[ERROR] Missing required environment variables: service_id and service_data"
  exit 1
fi

PYTHON_SCRIPT="/app/src/service_enrichment/enrich_and_index.py"

echo "[INFO] Enriching service: $service_id"

# Install uv if not found
UV_BIN="/root/.local/bin/uv"
if [ ! -f "$UV_BIN" ]; then
    echo "[UV] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || {
        echo "[ERROR] Failed to install uv"
        exit 1
    }
fi

# Activate Python virtual environment
VENV_PATH="/app/python_virtual_env"
echo "[VENV] Activating virtual environment at: $VENV_PATH"
source "$VENV_PATH/bin/activate" || {
    echo "[ERROR] Failed to activate virtual environment"
    exit 1
}

# Install required packages
echo "[PACKAGES] Installing required packages..."

"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "openai>=1.12.0" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "qdrant-client>=1.15.1" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "pydantic>=2.11.7" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "loguru>=0.7.3" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "python-dotenv>=1.0.0" || exit 1

echo "[PACKAGES] All packages installed successfully"

# Set Python path
export PYTHONPATH="/app:/app/src:$PYTHONPATH"

# Check if script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "[ERROR] Python script not found: $PYTHON_SCRIPT"
    exit 1
fi

# Execute Python enrichment script
echo "[EXECUTION] Running enrichment script..."
python3 "$PYTHON_SCRIPT" \
    --service-id "$service_id" \
    --service-data "$service_data"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "[SUCCESS] Service enrichment completed successfully"
else
    echo "[ERROR] Service enrichment failed with exit code: $exit_code"
fi

exit $exit_code
```

### 2.5 Python Enrichment Script (NEW)

**File**: `src/service_enrichment/enrich_and_index.py`

This is the core enrichment logic - will be detailed in Section 3.

---

## 3. Enrichment Logic

### 3.1 Enrichment Prompt

The LLM receives the service data and generates enriched context.

**Prompt Template:**

```python
ENRICHMENT_PROMPT = """
You are a service intent enrichment assistant. Your task is to expand and enhance service descriptions to improve semantic search and intent classification.

Given a service description, generate:
1. **Synonyms**: Alternative words/phrases with the same meaning
2. **Related Terms**: Contextually related concepts
3. **Query Variations**: Different ways users might ask for this service
4. **Entity Context**: Additional context about expected entities

---

SERVICE INFORMATION:
- Name: {service_name}
- Description: {service_description}
- Examples: {service_examples}
- Expected Entities: {service_entities}

---

TASK:
Generate enriched context that will help match user queries to this service.

RESPONSE FORMAT (JSON only):
{{
  "synonyms": ["synonym1", "synonym2", ...],
  "related_terms": ["term1", "term2", ...],
  "query_variations": ["variation1", "variation2", ...],
  "entity_context": {{
    "entity_name_1": "brief description of what this entity represents",
    "entity_name_2": "brief description of what this entity represents"
  }}
}}

GUIDELINES:
- Focus on semantic similarity and user intent
- Include common misspellings and colloquialisms if relevant
- Keep language natural and conversational
- Generate 5-10 items per category
- Maintain consistency with the service's actual purpose
- Output ONLY valid JSON, no explanations

EXAMPLE OUTPUT:
{{
  "synonyms": ["exchange rate", "currency conversion", "forex rate"],
  "related_terms": ["EUR to USD", "currency pair", "forex", "money exchange"],
  "query_variations": [
    "what is the current exchange rate",
    "convert EUR to USD",
    "how much is one euro in dollars",
    "EUR USD rate today"
  ],
  "entity_context": {{
    "from_currency": "The currency code to convert from (e.g., EUR, USD, GBP)",
    "to_currency": "The currency code to convert to (e.g., EUR, USD, GBP)"
  }}
}}
"""
```

### 3.2 Embedding Text Construction

After enrichment, construct the final text for embedding:

```python
def construct_enriched_embedding_text(
    service_data: Dict,
    enrichment: Dict
) -> str:
    """
    Construct embedding text from service data and enriched context.
    
    Format:
    - Original description
    - Original examples
    - Enriched synonyms
    - Enriched related terms
    - Enriched query variations
    - Entity context
    
    All sections newline-separated for optimal embedding.
    """
    parts = []
    
    # Original description
    parts.append(service_data['description'])
    
    # Original examples
    if service_data.get('examples'):
        parts.extend(service_data['examples'])
    
    # Enriched synonyms
    if enrichment.get('synonyms'):
        parts.extend(enrichment['synonyms'])
    
    # Enriched related terms
    if enrichment.get('related_terms'):
        parts.extend(enrichment['related_terms'])
    
    # Enriched query variations
    if enrichment.get('query_variations'):
        parts.extend(enrichment['query_variations'])
    
    # Entity context (formatted as descriptions)
    if enrichment.get('entity_context'):
        for entity, context in enrichment['entity_context'].items():
            parts.append(f"{entity}: {context}")
    
    return "\n".join(parts)
```

**Example Output:**

```text
Kasutaja soovib infot ettevõtte poolt tasutud tööjõumaksude kohta, näiteks palgamaksud ja sotsiaalmaks.
ettevõtte tasutud tööjõumaksud
kui palju maksis ettevõte tööjõumakse
firma poolt tasutud tööjõumaksud
salary taxes
payroll taxes
workforce contributions
employer taxes
labor costs
social security contributions
payroll expenses
employee-related taxes
company tax obligations
kuidas palju tööjõumakse
ettevõtte maksud töötajate eest
tööjõukulud maksud
company_name: The registered name of the company or business registry code
tax_period: The time period for which tax information is requested (e.g., year, quarter)
```

### 3.3 Qdrant Document Structure

**Document Schema:**

```json
{
  "id": "common_service_companies_workforce_taxes",
  "name": "Ettevõtte tööjõumaksud",
  "description": "Kasutaja soovib infot ettevõtte poolt tasutud tööjõumaksude kohta...",
  "examples": [
    "ettevõtte tasutud tööjõumaksud",
    "kui palju maksis ettevõte tööjõumakse",
    "firma poolt tasutud tööjõumaksud"
  ],
  "entities": ["company_name"],
  "text_for_embedding": "... (full enriched text from section 3.2) ...",
  "service_id": "common_service_companies_workforce_taxes",
  "ruuter_type": "POST",
  "current_state": "active",
  "is_enriched": true,
  "enriched_at": "2026-02-19T10:30:00Z",
  "enrichment_version": "1.0"
}
```

### 3.4 Fallback Strategy

If LLM enrichment fails:

```python
def construct_fallback_embedding_text(service_data: Dict) -> str:
    """
    Fallback: Use original data without enrichment.
    """
    parts = [service_data['description']]
    parts.extend(service_data.get('examples', []))
    return "\n".join(parts)
```

---

## 4. Python Script Implementation

### 4.1 Script Structure

```
src/service_enrichment/
├── __init__.py
├── enrich_and_index.py          # Main script (CLI entry point)
├── enrichment_service.py        # LLM enrichment logic
├── qdrant_indexer.py            # Qdrant upsert logic
└── models.py                    # Pydantic models
```

### 4.2 Main Script Flow

```python
"""
Main enrichment script: enrich_and_index.py

Steps:
1. Parse command-line arguments (service_id, service_data JSON)
2. Load configuration (LLM connection, Qdrant connection)
3. Call LLM to enrich service data
4. Construct enriched embedding text
5. Generate vector embedding (OpenAI text-embedding-3-large)
6. Upsert document into Qdrant intent_collection
7. Return success/failure response
"""

import sys
import json
import argparse
from typing import Dict, Optional
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add(sys.stderr, level="ERROR")


def main():
    parser = argparse.ArgumentParser(description="Enrich and index service data")
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--service-data", required=True)
    args = parser.parse_args()
    
    try:
        # Parse service data
        service_data = json.loads(args.service_data)
        logger.info(f"Processing service: {args.service_id}")
        
        # Load configuration
        config = load_configuration()
        
        # Initialize components
        enrichment_service = EnrichmentService(config)
        qdrant_indexer = QdrantIndexer(config)
        
        # Step 1: Enrich service data
        enrichment = enrichment_service.enrich(service_data)
        
        # Step 2: Construct embedding text
        embedding_text = construct_enriched_embedding_text(
            service_data, enrichment
        )
        
        # Step 3: Generate vector embedding
        embedding_vector = enrichment_service.generate_embedding(
            embedding_text
        )
        
        # Step 4: Prepare Qdrant document
        qdrant_doc = prepare_qdrant_document(
            service_data, embedding_text, enrichment
        )
        
        # Step 5: Upsert into Qdrant
        qdrant_indexer.upsert(
            collection_name="intent_collection",
            document_id=args.service_id,
            vector=embedding_vector,
            payload=qdrant_doc
        )
        
        logger.info(f"Successfully enriched and indexed service: {args.service_id}")
        
        # Output success JSON
        print(json.dumps({
            "success": True,
            "service_id": args.service_id,
            "enriched": True,
            "embedding_dimension": len(embedding_vector)
        }))
        
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        print(json.dumps({
            "success": False,
            "error": str(e),
            "service_id": args.service_id
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## 5. Configuration

### 5.1 Required Environment Variables

```bash
# LLM Configuration (OpenAI)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini  # For enrichment LLM calls
OPENAI_EMBEDDING_MODEL=text-embedding-3-large

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=  # Optional

# Intent Collection
INTENT_COLLECTION_NAME=intent_collection
INTENT_COLLECTION_DIMENSION=3072  # text-embedding-3-large dimension
```

### 5.2 LLM Connection

Use existing `llm_connections` table or Vault integration:

```python
# Option 1: Fetch from llm_connections table
connection = fetch_production_connection(connection_type="openai")

# Option 2: Use environment variables directly
config = {
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_BASE_URL"),
    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
}
```

---

## 6. API Usage Examples

### 6.1 Enrich Single Service

```bash
POST http://localhost:8080/rag-search/services/enrich
Content-Type: application/json

{
  "service_id": "common_service_companies_workforce_taxes",
  "name": "Ettevõtte tööjõumaksud",
  "description": "Kasutaja soovib infot ettevõtte poolt tasutud tööjõumaksude kohta, näiteks palgamaksud ja sotsiaalmaks.",
  "examples": [
    "ettevõtte tasutud tööjõumaksud",
    "kui palju maksis ettevõte tööjõumakse",
    "firma poolt tasutud tööjõumaksud"
  ],
  "entities": ["company_name"],
  "ruuter_type": "POST",
  "current_state": "active",
  "is_common": true
}
```

**Response (Success):**

```json
{
  "success": true,
  "service_id": "common_service_companies_workforce_taxes",
  "message": "Service enriched and indexed successfully",
  "enrichment_details": {
    "success": true,
    "service_id": "common_service_companies_workforce_taxes",
    "enriched": true,
    "embedding_dimension": 3072
  }
}
```

**Response (Error - Missing Required Field):**

```json
{
  "success": false,
  "error": "MISSING_DESCRIPTION",
  "message": "description is required"
}
```

### 6.2 Integration with Service Creation

When creating a service via admin API:

```python
# Step 1: Insert service into PostgreSQL
service_data = {
    "service_id": "exchange-rate-001",
    "name": "Exchange Rate Service",
    "description": "Returns current exchange rate between two currencies",
    "examples": ["EUR to USD rate", "convert EUR to USD"],
    "entities": ["from_currency", "to_currency"],
    "ruuter_type": "GET",
    "current_state": "active",
    "is_common": False
}
insert_service_into_db(service_data)

# Step 2: Trigger enrichment (pass service_data directly)
response = requests.post(
    "http://localhost:8080/rag-search/services/enrich",
    json=service_data  # Send complete service data
)

if response.json()["success"]:
    logger.info(f"Service {service_data['service_id']} enriched and indexed")
else:
    logger.error(f"Enrichment failed: {response.json()['error']}")
```

---

## 7. Error Handling

### 7.1 Error Scenarios

| Scenario | HTTP Status | Error Code | Response |
|----------|-------------|------------|----------|
| Missing service_id | 400 | `MISSING_SERVICE_ID` | `{"success": false, "error": "MISSING_SERVICE_ID", ...}` |
| Missing name | 400 | `MISSING_NAME` | `{"success": false, "error": "MISSING_NAME", ...}` |
| Missing description | 400 | `MISSING_DESCRIPTION` | `{"success": false, "error": "MISSING_DESCRIPTION", ...}` |
| LLM enrichment failed | 500 | `LLM_ENRICHMENT_FAILED` | Fallback to original data |
| Embedding generation failed | 500 | `EMBEDDING_FAILED` | `{"success": false, "error": "EMBEDDING_FAILED", ...}` |
| Qdrant upsert failed | 500 | `INDEXING_FAILED` | `{"success": false, "error": "INDEXING_FAILED", ...}` |

### 7.2 Retry Strategy

```python
# Retry LLM enrichment (max 3 attempts)
for attempt in range(3):
    try:
        enrichment = llm_enrichment_service.enrich(service_data)
        break
    except Exception as e:
        if attempt == 2:
            logger.warning("LLM enrichment failed, using fallback")
            enrichment = {}  # Use fallback
        else:
            time.sleep(2 ** attempt)  # Exponential backoff

# No retry for Qdrant (immediate failure)
```

---

## 8. Monitoring & Logging

### 8.1 Log Events

```python
# Key log events
logger.info(f"[ENRICHMENT_START] service_id={service_id}")
logger.info(f"[LLM_ENRICHMENT] Generated {len(enrichment['synonyms'])} synonyms")
logger.info(f"[EMBEDDING] Dimension: {len(embedding_vector)}")
logger.info(f"[QDRANT_UPSERT] Collection: intent_collection, ID: {service_id}")
logger.info(f"[ENRICHMENT_SUCCESS] service_id={service_id}, duration={duration}ms")
logger.error(f"[ENRICHMENT_FAILED] service_id={service_id}, error={error}")
```

### 8.2 Metrics to Track

```python
# Future: Add metrics collection
metrics = {
    "total_services_enriched": 0,
    "enrichment_failures": 0,
    "average_enrichment_time_ms": 0,
    "llm_token_usage": {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_cost_usd": 0.0
    }
}
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# Test enrichment logic
def test_construct_enriched_embedding_text():
    service_data = {...}
    enrichment = {...}
    result = construct_enriched_embedding_text(service_data, enrichment)
    assert "synonyms" in result
    assert "related_terms" in result

# Test fallback strategy
def test_fallback_on_llm_failure():
    service_data = {...}
    result = construct_fallback_embedding_text(service_data)
    assert service_data['description'] in result
```

### 9.2 Integration Tests

```bash
# Test full pipeline
curl -X POST http://localhost:8080/rag-search/services/enrich \
  -H "Content-Type: application/json" \
  -d '{"service_id": "test-service-001"}'

# Verify in Qdrant
curl http://localhost:6333/collections/intent_collection/points/test-service-001
```

### 9.3 Test Service Data

```sql
-- Insert test service
INSERT INTO public.services (
    service_id, name, description, examples, entities, ruuter_type, current_state
) VALUES (
    'test-service-001',
    'Test Exchange Rate Service',
    'Returns current exchange rate between two currencies',
    ARRAY['EUR to USD rate', 'convert EUR to USD'],
    ARRAY['from_currency', 'to_currency'],
    'GET',
    'active'
);
```

---

## 10. Implementation Checklist

### Phase 1: Ruuter Endpoint
- [ ] Create Ruuter endpoint: `services/enrich.yml`
- [ ] Test endpoint with mock service data payload
- [ ] Verify error handling (missing fields, validation)

### Phase 2: CronManager Configuration
- [ ] Create CronManager DSL: `service_enrichment.yml`
- [ ] Create shell script: `service_enrichment.sh`
- [ ] Test shell script execution manually

### Phase 3: Python Enrichment Script
- [ ] Create module structure: `src/service_enrichment/`
- [ ] Implement `enrich_and_index.py` (main script)
- [ ] Implement `enrichment_service.py` (LLM logic)
- [ ] Implement `qdrant_indexer.py` (Qdrant operations)
- [ ] Implement `models.py` (Pydantic models)
- [ ] Add unit tests

### Phase 4: Integration Testing
- [ ] Test full pipeline end-to-end
- [ ] Verify Qdrant documents match schema
- [ ] Test error scenarios (missing fields, LLM failure, etc.)
- [ ] Test fallback strategy

### Phase 5: Documentation
- [ ] Add API endpoint to `endpoints.md`
- [ ] Update README with enrichment pipeline section
- [ ] Create usage examples

---

## 11. Future Enhancements

### 11.1 Batch Enrichment

```bash
POST /rag-search/services/enrich-batch
{
  "service_ids": [
    "service-001",
    "service-002",
    "service-003"
  ]
}
```

### 11.2 Re-enrichment Strategy

```bash
# Re-enrich all active services
POST /rag-search/services/re-enrich-all
{
  "force": true,  # Re-enrich even if already enriched
  "state_filter": "active"  # Only active services
}
```

### 11.3 Enrichment Quality Scoring

Track enrichment quality metrics:

```python
quality_score = {
    "synonym_diversity": 0.85,  # Unique vs. total synonyms
    "query_variation_coverage": 0.90,  # Coverage of expected queries
    "embedding_quality": 0.88  # Cosine similarity to original
}
```

---

## 12. Open Questions

1. **LLM Model Choice**: Should we use `gpt-4o-mini` for cost efficiency or `gpt-4o` for better quality?
   - **Recommendation**: Start with `gpt-4o-mini`, monitor quality, upgrade if needed

2. **Enrichment Versioning**: Should we track enrichment versions for re-enrichment?
   - **Recommendation**: Add `enrichment_version` field to Qdrant payload

3. **Multi-language Support**: Should enrichment handle Estonian vs. English differently?
   - **Recommendation**: Single prompt works for both, LLM detects language automatically

4. **Caching Strategy**: Should we cache enriched data in PostgreSQL?
   - **Recommendation**: No - Qdrant is the source of truth for enriched data

---

## 13. Summary

This specification defines a **synchronous, LLM-based service enrichment pipeline** that:

1. ✅ Receives service data via REST API
2. ✅ Enriches data using LLM (synonyms, related terms, query variations)
3. ✅ Generates vector embeddings using OpenAI text-embedding-3-large
4. ✅ Upserts enriched documents into Qdrant intent_collection
5. ✅ Provides graceful fallback if enrichment fails
6. ✅ Returns synchronous success/error response

**Next Step**: Await user confirmation before implementation.

---
