"""Test script for the prompt refiner integration."""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import after path setup
from models.request_models import OrchestrationRequest, ConversationItem  # type: ignore[import-untyped]
from llm_orchestration_service import LLMOrchestrationService  # type: ignore[import-untyped]


def test_integration():
    """Test the orchestration service with prompt refiner integration."""
    print("Testing LLM Orchestration Service with Prompt Refiner...")

    # Create test request
    test_request = OrchestrationRequest(
        chatId="test-chat-123",
        message="I need help with my electricity bill payment.",
        authorId="test-user",
        conversationHistory=[
            ConversationItem(
                authorRole="user",
                message="Hello, I have a question about my bill",
                timestamp="2025-09-11T10:00:00Z",
            ),
            ConversationItem(
                authorRole="bot",
                message="I'm here to help with your billing questions. What specific issue do you have?",
                timestamp="2025-09-11T10:00:30Z",
            ),
        ],
        url="gov.ee",
        environment="development",
        connection_id="test-conn-123",
    )

    try:
        # Test the orchestration service
        service = LLMOrchestrationService()
        response = service.process_orchestration_request(test_request)

        print("✅ Integration test successful!")
        print(f"Response: {response}")

    except Exception as e:
        print(f"❌ Integration test failed: {str(e)}")
        import traceback

        print(traceback.format_exc())


if __name__ == "__main__":
    test_integration()
