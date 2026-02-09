# Custom Prompt Configuration Flow

## Overview

The custom prompt configuration system allows admins to configure prompts via UI that automatically apply to all response generation operations. Changes are cached with a 5-minute TTL and can be immediately refreshed when updated.

---

## Architecture Components

### 1. **Database Layer**
- **Table**: `public.prompt_configuration`
- **Columns**: `id` (BIGINT), `prompt` (TEXT)
- Stores the custom prompt text configured by admins

### 2. **Ruuter DSL Endpoints**
- **Get Prompt**: `DSL/Ruuter.public/rag-search/POST/llm-connections/prompts/get-prompt.yml`
  - Fetches prompt from database via Resql
  - Returns prompt data or empty object

- **Save Prompt**: `DSL/Ruuter.private/rag-search/POST/prompt-configuration/save.yml`
  - Updates/inserts prompt in database
  - Automatically triggers cache refresh after save

### 3. **Python Components**
- **PromptConfigurationLoader** (`src/utils/prompt_config_loader.py`)
  - HTTP client to fetch prompts via Ruuter
  - 5-minute TTL cache with thread safety
  - Retry logic (3 attempts, exponential backoff)
  - Force refresh capability

- **LLMOrchestrationService** (`src/llm_orchestration_service.py`)
  - Initializes loader at startup
  - Formats custom instructions with wrapper tags
  - Passes to ResponseGeneratorAgent

- **ResponseGeneratorAgent** (`src/response_generator/response_generate.py`)
  - Accepts `custom_instructions_prefix` parameter
  - Prepends custom instructions to user questions
  - Applied in both streaming and non-streaming modes

### 4. **API Endpoints**
- **`POST /orchestrate`** - Standard request flow
- **`POST /orchestrate/test`** - Test request flow
- **`POST /orchestrate/stream`** - Streaming request flow
- **`POST /prompt-config/refresh`** - Force cache refresh

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ ADMIN UPDATES PROMPT IN UI                                      │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Ruuter: save.yml                                                │
│  1. Update/Insert in PostgreSQL                                 │
│  2. Call POST /prompt-config/refresh                            │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI: /prompt-config/refresh                                 │
│  - PromptConfigurationLoader.force_refresh()                    │
│  - Invalidates cache immediately                                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Cache Updated - Ready for Next Request                          │
└─────────────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════╗
║ USER SENDS MESSAGE                                              ║
╚════════════════┬════════════════════════════════════════════════╝
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI: /orchestrate, /orchestrate/test, or /orchestrate/stream│
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LLMOrchestrationService.process_orchestration_request()         │
│ or stream_orchestration_response()                              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ _initialize_service_components()                                │
│  ↓                                                               │
│ _safe_initialize_response_generator()                           │
│  ↓                                                               │
│ _initialize_response_generator()                                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ _get_custom_instructions_for_response_generation()              │
│  ↓                                                               │
│ prompt_config_loader.get_custom_instructions()                  │
│  - Returns from cache if valid (< 5 min old)                    │
│  - OR fetches via Ruuter if expired                             │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Format custom instructions:                                     │
│ "[SYSTEM INSTRUCTIONS]\n{prompt}\n\n[USER QUESTION]\n"          │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ResponseGeneratorAgent(custom_instructions_prefix=prefix)       │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ResponseGeneratorAgent.forward() or stream_response()          │
│  - Prepends custom_instructions_prefix to user question         │
│  - Modified question = "{prefix}{user_question}"                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ DSPy Predictor receives modified question                       │
│  - Custom instructions guide response generation                │
│  - LLM follows configured rules (language, tone, format, etc.)  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Response returned to user                                       │
│  - Follows custom prompt configuration                          │
│  - Language policy applied                                      │
│  - Formatting rules applied                                     │
│  - Safety guidelines applied                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Detailed Step-by-Step Flow

### **Startup Phase**
1. **Service Initialization** (`LLMOrchestrationService.__init__`)
   - Creates `PromptConfigurationLoader` instance
   - Warms up cache by calling `get_custom_instructions()`
   - Logs success: "✅ Custom prompt configuration loaded at startup (X chars)"

### **Admin Updates Prompt**
1. **UI Save Action**
   - Admin edits prompt text in UI
   - Submits save request

2. **Ruuter Processing** (`save.yml`)
   - Checks if prompt exists in database
   - Updates existing or inserts new prompt
   - Calls `POST /prompt-config/refresh` endpoint

3. **Cache Invalidation** (`/prompt-config/refresh`)
   - `force_refresh()` clears cache immediately
   - Fetches new prompt from Ruuter
   - Returns success status with prompt preview

### **User Request Processing**
1. **Request Received** (Any of 3 endpoints)
   - `/orchestrate` - Standard response
   - `/orchestrate/test` - Test response
   - `/orchestrate/stream` - Streaming response

2. **Service Components Initialization**
   - LLM Manager initialized
   - Contextual Retriever initialized
   - **Response Generator initialized** ← Custom prompt applied here

3. **Custom Instructions Loading**
   ```python
   custom_prefix = self._get_custom_instructions_for_response_generation()
   # Returns: "[SYSTEM INSTRUCTIONS]\n{prompt}\n\n[USER QUESTION]\n"
   ```

4. **Response Generator Creation**
   ```python
   ResponseGeneratorAgent(custom_instructions_prefix=custom_prefix)
   ```

5. **Question Modification**
   ```python
   # In forward() or stream_response()
   modified_question = f"{custom_instructions_prefix}{user_question}"
   ```

6. **LLM Processing**
   - DSPy predictor receives modified question
   - Custom instructions guide response behavior
   - Response generated following configured rules

---

## Cache Behavior

### **TTL Cache (5 minutes)**
- **Cache Hit**: Returns immediately from memory (fast)
- **Cache Miss**: Fetches via HTTP from Ruuter (slower, ~100-500ms)
- **Stale Fallback**: If fetch fails, returns last known good value

### **Force Refresh**
- Triggered by admin save action
- Bypasses cache TTL
- Ensures immediate propagation of changes

### **Thread Safety**
- Uses `threading.Lock()` for concurrent requests
- Single fetch for multiple simultaneous requests
- Cache shared across all requests

---

## Configuration

### **Constants** (`src/llm_orchestrator_config/llm_ochestrator_constants.py`)
```python
RUUTER_PROMPT_CONFIG_ENDPOINT = "[#RAG_SEARCH_RUUTER_PUBLIC]/llm-connections/prompts/get-prompt"
PROMPT_CONFIG_CACHE_TTL = 300  # 5 minutes
```

### **Environment Variables** (`constants.ini`)
```ini
RAG_SEARCH_PROMPT_REFRESH=http://llm-orchestration-service:8100/prompt-config/refresh
```

---

## Testing

### **1. Insert Test Prompt**
```sql
INSERT INTO public.prompt_configuration (id, prompt)
VALUES (1, 'Always respond in Estonian language. Be professional and concise.')
ON CONFLICT (id) DO UPDATE SET prompt = EXCLUDED.prompt;
```

### **2. Test via API**
```bash
curl -X POST http://localhost:8100/orchestrate/test \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is artificial intelligence?",
    "environment": "development",
    "connectionId": 1
  }'
```

### **3. Update Prompt**
```sql
UPDATE public.prompt_configuration
SET prompt = 'Provide concise answers using bullet points. Be helpful and clear.'
WHERE id = 1;
```

### **4. Verify Immediate Refresh**
- Check logs for: "✅ Prompt configuration cache refreshed successfully"
- Test same question - response format should change immediately

### **5. Check Cache Status**
```bash
# Manual refresh (optional)
curl -X POST http://localhost:8100/prompt-config/refresh
```

---

## Key Features

✅ **TTL Caching** - 5-minute cache reduces database calls  
✅ **Immediate Updates** - Admin changes trigger instant refresh  
✅ **Graceful Degradation** - If refresh fails, TTL cache continues working  
✅ **Thread-Safe** - Multiple concurrent requests handled safely  
✅ **Retry Logic** - 3 attempts with exponential backoff for HTTP failures  
✅ **Instruction Prepending** - Preserves DSPy optimization compatibility  
✅ **Applied Consistently** - Works across all 3 orchestration endpoints  
✅ **Applied to ResponseGenerator Only** - Not applied to PromptRefinerAgent

---

## Example

**Database Prompt:**
```
Always respond in Estonian language. Be professional and concise. 
When answering, prioritize accuracy and cite sources when available.
```

**What DSPy Receives:**
```
[SYSTEM INSTRUCTIONS]
Always respond in Estonian language. Be professional and concise. 
When answering, prioritize accuracy and cite sources when available.

[USER QUESTION]
What is DigiDoc and how can I use it?

Context: [retrieved documentation chunks...]
```

**Expected Response:**
- In Estonian language ✅
- Professional tone ✅
- Concise format ✅
- Citations included ✅

---

## Files Modified

| File | Purpose |
|------|---------|
| `src/utils/prompt_config_loader.py` | HTTP loader with caching and retry |
| `src/llm_orchestration_service.py` | Initialize loader, format instructions |
| `src/llm_orchestration_service_api.py` | Refresh endpoint |
| `src/response_generator/response_generate.py` | Accept and apply custom prefix |
| `DSL/Ruuter.public/rag-search/POST/llm-connections/prompts/get-prompt.yml` | Fetch prompt endpoint |
| `DSL/Ruuter.private/rag-search/POST/prompt-configuration/save.yml` | Save with refresh trigger |
| `src/llm_orchestrator_config/llm_ochestrator_constants.py` | Configuration constants |
| `constants.ini` | Refresh endpoint URL |

---

## Troubleshooting

### **Prompt Not Applied**
- Check logs for: "✅ Custom prompt configuration loaded"
- Verify database has prompt: `SELECT * FROM public.prompt_configuration;`
- Test refresh endpoint: `curl -X POST http://localhost:8100/prompt-config/refresh`

### **Cache Not Refreshing**
- Check Ruuter save.yml calls refresh endpoint
- Verify `RAG_SEARCH_PROMPT_REFRESH` constant in constants.ini
- Check logs for refresh success/failure

### **Empty Prompt**
- Check Ruuter endpoint returns correct format
- Verify response unwrapping logic in loader
- Check logs for "⚠️ No custom prompt configuration found"

---

## Notes

- Custom prompts apply **only to ResponseGeneratorAgent** (not PromptRefinerAgent)
- PromptRefiner focuses on query optimization for retrieval
- ResponseGenerator needs language policy and interaction style for user-facing content
- This design preserves DSPy optimization compatibility by using instruction prepending instead of signature modification
