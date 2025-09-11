# LLM Orchestration Service API

A FastAPI-based service for orchestrating LLM requests with configuration management and proper validation.

## API Endpoints

### POST /orchestrate
Processes LLM orchestration requests.

**Request Body:**
```json
{
    "chatId": "chat-12345",
    "message": "I need help with my electricity bill.",
    "authorId": "12345",
    "conversationHistory": [
        {
            "authorRole": "user",
            "message": "Hi, I have a billing issue",
            "timestamp": "2025-04-29T09:00:00Z"
        },
        {
            "authorRole": "bot",
            "message": "Sure, can you tell me more about the issue?",
            "timestamp": "2025-04-29T09:00:05Z"
        }
    ],
    "url": "id.ee",
    "environment": "production|test|development",
    "connection_id": "optional-connection-id"
}
```

**Response:**
```json
{
    "chatId": "chat-12345",
    "llmServiceActive": true,
    "questionOutOfLLMScope": false,
    "inputGuardFailed": false,
    "content": "This is a random answer payload.\n\nwith citations.\n\nReferences\n- https://gov.ee/sample1,\n- https://gov.ee/sample2"
}
```

### GET /health
Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "llm-orchestration-service"
}
```

## Running the API

### Local Development:
```bash
uv run uvicorn src.llm_orchestration_service_api:app --host 0.0.0.0 --port 8100 --reload
```

### Docker (Standalone):
```bash
# Build and run with custom script
.\build-llm-service.bat run       # Windows
./build-llm-service.sh run        # Linux/Mac

# Or manually
docker build -f Dockerfile.llm_orchestration_service -t llm-orchestration-service .
docker run -p 8100:8100 --env-file .env llm-orchestration-service
```

### Docker Compose (Production):
```bash
docker-compose up llm-orchestration-service
```

### Docker Compose (Development with hot reload):
```bash
docker-compose -f docker-compose.yml -f docker-compose.llm-dev.yml up llm-orchestration-service
```

### Test the API:
```bash
uv run python test_api.py
```

## Features

- ✅ FastAPI with automatic OpenAPI documentation
- ✅ Pydantic validation for requests/responses
- ✅ Proper error handling and logging with Loguru
- ✅ Integration with existing LLM config module
- ✅ Type-safe implementation
- ✅ Health check endpoint
- 🔄 Hardcoded responses (TODO: Implement actual LLM pipeline)

## Documentation

When the server is running, visit:
- API docs: http://localhost:8100/docs
- ReDoc: http://localhost:8100/redoc

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                     │
│                (llm_orchestration_service_api.py)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                Business Logic Service                      │
│                (llm_orchestration_service.py)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  LLM Config Module                         │
│                   (llm_manager.py)                         │
└─────────────────────────────────────────────────────────────┘
```

## TODO Items

- [ ] Implement actual LLM processing pipeline
- [ ] Add input validation and guard checks
- [ ] Implement question scope validation
- [ ] Add proper citation generation
- [ ] Handle multi-tenant scenarios with connection_id
- [ ] Add authentication/authorization
- [ ] Add comprehensive error handling
- [ ] Add request/response logging
- [ ] Add metrics and monitoring
