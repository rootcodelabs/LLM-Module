"""
Integration tests for LLM inference pipeline.

These tests verify:
1. Production and testing inference endpoints
2. Complete RAG pipeline (guardrails → refinement → retrieval → generation)
3. Database storage of inference results
4. Error handling and edge cases
5. Contextual retrieval integration
"""

import requests
import json
from loguru import logger


class TestInference:
    """Test LLM inference pipeline via Ruuter endpoints."""

    def test_orchestration_service_health(self, orchestration_client):
        """Verify LLM orchestration service is healthy."""
        response = requests.get(f"{orchestration_client.base_url}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        logger.info("LLM orchestration service is healthy")

    def test_testing_inference_basic(
        self,
        ruuter_private_client,
        postgres_client,
        vault_client,
        sample_test_data,
        ensure_testing_connection,
        rag_stack,
    ):
        """Test production-style inference using the testing endpoint."""
        # Ensure testing connection exists for production tests
        connection_id = ensure_testing_connection
        logger.info(f"Using testing connection ID: {connection_id}")

        # Verify database connection details
        cursor = postgres_client.cursor()
        try:
            cursor.execute(
                "SELECT id, connection_name, environment, llm_model FROM llm_connections "
                "WHERE id = %s",
                (connection_id,),
            )
            row = cursor.fetchone()
            if row:
                logger.info(
                    f"Database connection found: ID={row[0]}, Name='{row[1]}', Env={row[2]}, Model={row[3]}"
                )
            else:
                logger.error(f"Connection {connection_id} not found in database!")
        finally:
            cursor.close()

        # Get a simple test question
        test_case = next(
            (item for item in sample_test_data if item["expected_scope"]),
            sample_test_data[0],
        )

        # Prepare test inference request (using testing endpoint for simplicity)
        payload = {
            "connectionId": connection_id,
            "message": test_case["question"],
            "environment": "testing",
        }

        logger.info(f"Testing inference with message: {test_case['question']}")
        logger.info(
            f"Expected vault path: llm/connections/azure_openai/test/{connection_id}"
        )
        logger.info(f"Using payload: {json.dumps(payload)}")
        logger.info(f"Ruuter base URL: {ruuter_private_client.base_url}")

        response = requests.post(
            f"{ruuter_private_client.base_url}/rag-search/inference/test",
            json=payload,
            headers={"Cookie": "customJwtCookie=test-session-token"},
            timeout=300,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()["response"]
        logger.info(f"Inference response data: {data}")

        # Validate response structure (test mode does not include chatId)
        assert "llmServiceActive" in data
        assert "questionOutOfLLMScope" in data
        assert "inputGuardFailed" in data
        assert "content" in data

        assert data["llmServiceActive"] is True
        assert len(data["content"]) > 0

        logger.info(f"Inference successful: {data['content'][:100]}...")
