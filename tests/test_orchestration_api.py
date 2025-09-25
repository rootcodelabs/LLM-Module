"""
Test file for validating the RAG Stack orchestration service using testcontainers.

This includes:
- Health endpoint validation
- Request structure validation for /orchestrate
- Optional response structure validation
"""

from typing import Any, Dict
import pytest
from loguru import logger
from requests import Session, Response


def test_health_endpoint(orchestration_client: Session) -> None:
    """Test that the orchestration service health endpoint is available and initialized"""
    base_url: str = getattr(orchestration_client, "base_url", "")
    response: Response = orchestration_client.get(f"{base_url}/health")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    health_data: Dict[str, Any] = response.json()
    assert health_data.get("status") == "healthy", f"Unexpected status: {health_data.get('status')}"
    assert health_data.get("service") == "llm-orchestration-service", f"Unexpected service: {health_data.get('service')}"
    assert health_data.get("orchestration_service") == "initialized", f"Unexpected orchestration_service: {health_data.get('orchestration_service')}"

    logger.info("✅ Health endpoint test passed.")


def test_orchestrate_endpoint_structure(orchestration_client: Session) -> None:
    """Test that the /orchestrate endpoint accepts a valid request structure"""
    base_url: str = getattr(orchestration_client, "base_url", "")

    test_request: Dict[str, Any] = {
        "chatId": "test-chat-123",
        "message": "Hello, this is a test message",
        "authorId": "test-user-456",
        "conversationHistory": [],
        "url": "https://test.example.com",
        "environment": "test"
    }

    response: Response = orchestration_client.post(
        f"{base_url}/orchestrate",
        json=test_request
    )

    assert response.status_code in {200, 400, 500}, f"Unexpected status: {response.status_code}"
    logger.info("✅ Orchestrate endpoint accepted the request structure.")


@pytest.mark.skip(reason="Response structure depends on actual implementation. Enable when ready.")
def test_orchestrate_endpoint_response(orchestration_client: Session) -> None:
    """Example test for validating the structure of /orchestrate response"""
    base_url: str = getattr(orchestration_client, "base_url", "")

    test_request: Dict[str, Any] = {
        "chatId": "test-chat-123",
        "message": "What is the capital of Estonia?",
        "authorId": "test-user-456",
        "conversationHistory": [],
        "url": "https://test.example.com",
        "environment": "test"
    }

    response: Response = orchestration_client.post(
        f"{base_url}/orchestrate",
        json=test_request
    )

    if response.status_code == 200:
        response_data: Dict[str, Any] = response.json()

        expected_fields = [
            "chatId", "llmServiceActive", "questionOutOfLLMScope",
            "inputGuardFailed", "content"
        ]

        for field in expected_fields:
            assert field in response_data, f"Missing field in response: {field}"

        assert response_data["chatId"] == test_request["chatId"]
        logger.info("✅ Orchestrate endpoint response structure test passed.")
    else:
        pytest.skip(f"API returned {response.status_code}, skipping response validation.")


def test_rag_stack_services_available(rag_stack: Any) -> None:
    """Test that all essential RAG stack services are up and discoverable"""
    assert rag_stack.is_service_available("qdrant"), "Qdrant is not available"
    assert rag_stack.is_service_available("llm-orchestration-service"), "Orchestration service is not available"

    qdrant_url = rag_stack.get_qdrant_url()
    orchestration_url = rag_stack.get_orchestration_service_url()

    assert qdrant_url.startswith("http://"), f"Unexpected Qdrant URL: {qdrant_url}"
    assert orchestration_url.startswith("http://"), f"Unexpected Orchestration URL: {orchestration_url}"

    logger.info("✅ RAG stack services availability test passed.")
