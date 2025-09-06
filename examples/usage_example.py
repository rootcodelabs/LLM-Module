"""Usage examples for the LLM Config Module.

This file demonstrates various ways to use the LLM Config Module
for different scenarios and use cases.
"""

import os
from pathlib import Path

# Import the LLM Config Module
from src.llm_config_module import LLMManager, LLMProvider, ConfigurationError


def basic_usage_example() -> None:
    """Basic usage example with default configuration."""
    print("=== Basic Usage Example ===")

    try:
        # Initialize the LLM Manager (singleton)
        manager = LLMManager()

        # Get the default configured LLM provider
        llm = manager.get_llm()

        print(f"Using provider: {llm.provider_name}")
        print(f"Model info: {llm.get_model_info()}")

        # Generate text (this would make an actual API call)
        # response = llm.generate("Hello, how are you today?")
        # print(f"Response: {response}")

    except ConfigurationError as e:
        print(f"Configuration error: {e}")
        print(
            "Make sure you have a valid llm_config.yaml file and environment variables set"
        )


def specific_provider_example() -> None:
    """Example using a specific provider."""
    print("\n=== Specific Provider Example ===")

    try:
        manager = LLMManager()

        # Get available providers
        available = manager.get_available_providers()
        print(f"Available providers: {list(available.keys())}")

        # Use Azure OpenAI specifically
        if manager.is_provider_available(LLMProvider.AZURE_OPENAI):
            azure_llm = manager.get_llm(LLMProvider.AZURE_OPENAI)
            print(f"Azure OpenAI info: {azure_llm.get_model_info()}")
        else:
            print("Azure OpenAI provider is not available")

        # Use AWS Bedrock specifically
        if manager.is_provider_available(LLMProvider.AWS_BEDROCK):
            bedrock_llm = manager.get_llm(LLMProvider.AWS_BEDROCK)
            print(f"AWS Bedrock info: {bedrock_llm.get_model_info()}")
        else:
            print("AWS Bedrock provider is not available")

    except ConfigurationError as e:
        print(f"Configuration error: {e}")


def dspy_integration_example() -> None:
    """Example showing DSPY integration."""
    print("\n=== DSPY Integration Example ===")

    try:

        manager = LLMManager()

        # Configure DSPY with the default provider
        manager.configure_dspy()
        print("DSPY configured with default provider")

        # Or configure with a specific provider
        if manager.is_provider_available(LLMProvider.AZURE_OPENAI):
            manager.configure_dspy(LLMProvider.AZURE_OPENAI)
            print("DSPY configured with Azure OpenAI")

        # Now you can use DSPY as normal
        # signature = dspy.Signature("question -> answer")
        # predictor = dspy.Predict(signature)
        # result = predictor(question="What is the capital of France?")
        # print(f"DSPY result: {result}")

    except ImportError:
        print("DSPY not available")
    except ConfigurationError as e:
        print(f"Configuration error: {e}")


def custom_config_example() -> None:
    """Example using a custom configuration file."""
    print("\n=== Custom Configuration Example ===")

    # Path to the example configuration
    config_path = Path(__file__).parent / "llm_config_example.yaml"

    if config_path.exists():
        try:
            # Reset singleton to use new config
            LLMManager.reset_instance()

            # Initialize with custom config
            manager = LLMManager(str(config_path))

            print(f"Loaded configuration from: {config_path}")
            print(
                f"Available providers: {list(manager.get_available_providers().keys())}"
            )

        except ConfigurationError as e:
            print(f"Failed to load custom configuration: {e}")
    else:
        print(f"Example configuration file not found at: {config_path}")


def environment_variables_example() -> None:
    """Example showing environment variable usage."""
    print("\n=== Environment Variables Example ===")

    # Show which environment variables are expected
    required_vars = {
        "Azure OpenAI": [
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
        ],
        "AWS Bedrock": ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    }

    print("Required environment variables:")
    for provider, vars_list in required_vars.items():
        print(f"\n{provider}:")
        for var in vars_list:
            value = os.getenv(var, "NOT SET")
            # Don't print actual secrets, just show if they're set
            if "key" in var.lower() or "secret" in var.lower():
                status = "SET" if value != "NOT SET" else "NOT SET"
                print(f"  {var}: {status}")
            else:
                print(f"  {var}: {value}")


def error_handling_example() -> None:
    """Example showing error handling."""
    print("\n=== Error Handling Example ===")

    try:
        # Try to use a non-existent configuration file
        LLMManager.reset_instance()
        manager = LLMManager("/non/existent/config.yaml")

    except ConfigurationError as e:
        print(f"Expected configuration error: {e}")

    try:
        # Try to get a provider that doesn't exist
        manager = LLMManager()
        # This would raise an error if we tried to access an unavailable provider
        available = manager.get_available_providers()
        if not available:
            print("No providers are available - check your configuration")

    except ConfigurationError as e:
        print(f"Provider error: {e}")


def main() -> None:
    """Run all examples."""
    print("LLM Config Module Usage Examples")
    print("=" * 40)

    basic_usage_example()
    specific_provider_example()
    dspy_integration_example()
    custom_config_example()
    environment_variables_example()
    error_handling_example()

    print("\n" + "=" * 40)
    print("Examples completed!")
    print("\nTo use this module in your own code:")
    print("1. Copy examples/llm_config_example.yaml to your project")
    print("2. Set the required environment variables")
    print("3. Import and use LLMManager in your code")


if __name__ == "__main__":
    main()
