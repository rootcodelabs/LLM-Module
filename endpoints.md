LLM Connections API Endpoints

Base URL
/ruuter-private/llm/connections

1. Create LLM Connection

Endpoint

POST /ruuter-private/llm/connections/create

Request Body

{
  "llm_platform": "OpenAI",
  "llm_model": "GPT-4o",
  "llm_api_key": "your-api-key",
  "embedding_platform": "OpenAI",
  "embedding_model": "text-embedding-3-small",
  "embedding_api_key": "your-embedding-api-key",
  "monthly_budget": 1000.00,
  "deployment_environment": "Testing"
}


Response (201)

{
  "id": 1,
  "llm_platform": "OpenAI",
  "llm_model": "GPT-4o",
  "embedding_platform": "OpenAI",
  "embedding_model": "text-embedding-3-small",
  "monthly_budget": 1000.00,
  "deployment_environment": "Testing",
  "status": "active",
  "created_at": "2025-09-02T10:15:30.000Z",
  "updated_at": "2025-09-02T10:15:30.000Z"
}

2. Update LLM Connection

Endpoint

POST /ruuter-private/llm/connections/update


Request Body

{
  "llm_platform": "Azure AI",
  "llm_model": "GPT-4o-mini",
  "monthly_budget": 2000.00,
  "deployment_environment": "Production",
  "status": "inactive"
}


Response (200)

{
  "id": 1,
  "llm_platform": "Azure AI",
  "llm_model": "GPT-4o-mini",
  "monthly_budget": 2000.00,
  "deployment_environment": "Production",
  "status": "inactive",
  "created_at": "2025-09-02T10:15:30.000Z",
  "updated_at": "2025-09-02T11:00:00.000Z"
}

3. Delete LLM Connection

Endpoint

POST /ruuter-private/llm/connections/delete


Response (200)

{
  "operation_successful": true,
  "message": "LLM Connection deleted successfully",
  "status_code": 200
}

4. List All LLM Connections

Endpoint

GET /ruuter-private/llm/connections/list


Query Params (optional for filtering)

llm_platform → filter by LLM platform

llm_model → filter by LLM model

deployment_environment → filter by environment (Testing / Production)

Example

GET /ruuter-private/llm/connections/list?llm_platform=OpenAI&deployment_environment=Testing&model=GPT4


Response (200)

[
  {
    "id": 1,
    "llm_platform": "OpenAI",
    "llm_model": "GPT-4o",
    "embedding_platform": "OpenAI",
    "embedding_model": "text-embedding-3-small",
    "monthly_budget": 1000.00,
    "deployment_environment": "Testing",
    "status": "active",
    "created_at": "2025-09-02T10:15:30.000Z",
    "updated_at": "2025-09-02T10:15:30.000Z"
  }
]

5. Get Single LLM Connection

Endpoint

GET /ruuter-private/llm/connections/overview


Response (200)

{
  "id": 1,
  "llm_platform": "OpenAI",
  "llm_model": "GPT-4o",
  "embedding_platform": "OpenAI",
  "embedding_model": "text-embedding-3-small",
  "monthly_budget": 1000.00,
  "deployment_environment": "Testing",
  "status": "active",
  "created_at": "2025-09-02T10:15:30.000Z",
  "updated_at": "2025-09-02T10:15:30.000Z"
}



Inference Results API Endpoints


Base URL
/ruuter-private/inference/results

1. Store Inference Result

Endpoint

POST /ruuter-private/inference/results/store


Request Body

{
  "llm_connection_id": 1,
  "user_question": "What are the benefits of using LLMs?",
  "refined_questions": [
    "How do LLMs improve productivity?",
    "What are practical use cases of LLMs?"
  ],
  "conversation_history": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi! How can I help you?" }
  ],
  "ranked_chunks": [
    { "id": "chunk_1", "content": "LLMs help in summarization", "rank": 1 },
    { "id": "chunk_2", "content": "They improve Q&A systems", "rank": 2 }
  ],
  "embedding_scores": {
    "chunk_1": 0.92,
    "chunk_2": 0.85
  },
  "final_answer": "LLMs can improve productivity by summarizing large documents, enabling Q&A, and enhancing automation."
}


Response (201)

{
  "id": 10,
  "llm_connection_id": 1,
  "user_question": "What are the benefits of using LLMs?",
  "refined_questions": [
    "How do LLMs improve productivity?",
    "What are practical use cases of LLMs?"
  ],
  "conversation_history": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi! How can I help you?" }
  ],
  "ranked_chunks": [
    { "id": "chunk_1", "content": "LLMs help in summarization", "rank": 1 },
    { "id": "chunk_2", "content": "They improve Q&A systems", "rank": 2 }
  ],
  "embedding_scores": {
    "chunk_1": 0.92,
    "chunk_2": 0.85
  },
  "final_answer": "LLMs can improve productivity by summarizing large documents, enabling Q&A, and enhancing automation.",
  "created_at": "2025-09-02T12:15:00.000Z"
}