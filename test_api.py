"""Test script for the LLM Orchestration Service API."""

import json
import requests


def test_api():
    """Test the orchestration API endpoint."""
    # API endpoint
    url = "http://localhost:8100/orchestrate"

    # Test request payload
    test_payload = {
        "chatId": "chat-12345",
        "message": "I need help with my electricity bill.",
        "authorId": "12345",
        "conversationHistory": [
            {
                "authorRole": "user",
                "message": "Hi, I have a billing issue",
                "timestamp": "2025-04-29T09:00:00Z",
            },
            {
                "authorRole": "bot",
                "message": "Sure, can you tell me more about the issue?",
                "timestamp": "2025-04-29T09:00:05Z",
            },
        ],
        "url": "id.ee",
        "environment": "development",
        "connection_id": "test-connection-123",
    }

    try:
        print("Testing /orchestrate endpoint...")
        print(f"Request payload: {json.dumps(test_payload, indent=2)}")

        # Make the request
        response = requests.post(url, json=test_payload, timeout=30)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            response_data = response.json()
            print(f"Response Body: {json.dumps(response_data, indent=2)}")
            print("✅ API test successful!")
        else:
            print(f"❌ API test failed with status: {response.status_code}")
            print(f"Error: {response.text}")

    except requests.exceptions.ConnectionError:
        print(
            "❌ Could not connect to API. Make sure the server is running on port 8100"
        )
        print(
            "Run: uv run uvicorn src.llm_orchestration_service_api:app --host 0.0.0.0 --port 8100"
        )
    except Exception as e:
        print(f"❌ Error during API test: {str(e)}")


def test_health_check():
    """Test the health check endpoint."""
    try:
        print("\nTesting /health endpoint...")
        response = requests.get("http://localhost:8100/health", timeout=10)

        if response.status_code == 200:
            print(f"Health check response: {response.json()}")
            print("✅ Health check successful!")
        else:
            print(f"❌ Health check failed: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to health endpoint")
    except Exception as e:
        print(f"❌ Health check error: {str(e)}")


if __name__ == "__main__":
    print("LLM Orchestration Service API Test")
    print("=" * 50)

    test_health_check()
    test_api()

    print("\n" + "=" * 50)
    print("Test completed!")
