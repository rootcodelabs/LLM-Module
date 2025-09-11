"""Test script to validate prompt refiner output schema."""

import sys
import json
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


def test_prompt_refiner_schema():
    """Test the PromptRefinerOutput schema validation."""
    print("Testing PromptRefinerOutput Schema Validation...")

    try:
        # Import after path setup
        from models.request_models import PromptRefinerOutput  # type: ignore[import-untyped]

        # Test valid data that matches your required format
        valid_data = PromptRefinerOutput(
            original_question="How do I configure Azure embeddings?",
            refined_questions=[
                "Configure Azure OpenAI embedding endpoint",
                "Set Azure embedding deployment name",
                "Azure OpenAI embeddings API version requirements",
                "Provide API key for Azure embedding generator",
                "Azure OpenAI embedding configuration steps",
            ],
        )

        print("✅ Schema validation successful!")
        print(f"Original question: {valid_data.original_question}")
        print(f"Number of refined questions: {len(valid_data.refined_questions)}")
        print("\nRefined questions:")
        for i, question in enumerate(valid_data.refined_questions, 1):
            print(f"  {i}. {question}")

        # Test JSON serialization
        json_output = valid_data.model_dump()
        print("\n✅ JSON serialization successful!")
        print(f"JSON output:\n{json.dumps(json_output, indent=2)}")

        # Verify the exact format you requested
        expected_keys = {"original_question", "refined_questions"}
        actual_keys = set(json_output.keys())

        if expected_keys == actual_keys:
            print("✅ Output format matches exactly with required schema!")
        else:
            print(f"❌ Schema mismatch. Expected: {expected_keys}, Got: {actual_keys}")
            return False

        return True

    except Exception as e:
        print(f"❌ Schema validation failed: {str(e)}")
        import traceback

        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    print("Prompt Refiner Output Schema Validation Test")
    print("=" * 50)
    success = test_prompt_refiner_schema()
    print("\n" + "=" * 50)
    if success:
        print("✅ Schema validation test passed!")
    else:
        print("❌ Schema validation test failed!")
