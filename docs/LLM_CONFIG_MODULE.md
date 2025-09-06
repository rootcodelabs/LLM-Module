# LLM Config Module Documentation

## Overview

The LLM Config Module is a flexible, configurable system for managing different LLM providers with DSPY integration. It uses the Factory Method pattern and Singleton pattern to provide a clean, extensible architecture for working with multiple LLM providers.

## Features

- ✅ **Factory Method Pattern**: Clean separation between provider creation and usage
- ✅ **Singleton Manager**: Consistent access to LLM providers across your application
- ✅ **Configuration-Driven**: YAML configuration with environment variable support
- ✅ **DSPY Integration**: Seamless integration with DSPY framework
- ✅ **Type Safety**: Full type hints following strict typing standards
- ✅ **Extensible**: Easy to add new LLM providers
- ✅ **Error Handling**: Comprehensive error handling and validation

## Supported Providers

- **Azure OpenAI**: GPT-4o and other Azure OpenAI models
- **AWS Bedrock**: Anthropic Claude 3.5 Sonnet and other Bedrock models

## Architecture

```
LLMManager (Singleton)
├── ConfigurationLoader
│   ├── YAML Parser
│   └── Environment Variable Substitution
├── LLMFactory (Factory Pattern)
│   ├── AzureOpenAIProvider
│   └── AWSBedrockProvider
└── DSPY Integration
```

## Installation

1. Ensure you have the required dependencies in your `pyproject.toml`:

```toml
dependencies = [
    "dspy>=3.0.3",
    "pyyaml>=6.0,<7.0",
    "boto3>=1.34.0,<2.0",
    "openai>=1.0.0,<2.0",
    "azure-identity>=1.15.0,<2.0",
]
```

2. Install dependencies:

```bash
uv sync
```

## Quick Start

### 1. Configuration

Create a `llm_config.yaml` file (or copy from `examples/llm_config_example.yaml`):

```yaml
llm:
  default_provider: "azure_openai"
  
  providers:
    azure_openai:
      enabled: true
      model: "gpt-4o"
      api_version: "2024-02-15-preview"
      endpoint: "${AZURE_OPENAI_ENDPOINT}"
      api_key: "${AZURE_OPENAI_API_KEY}"
      deployment_name: "${AZURE_OPENAI_DEPLOYMENT_NAME}"
      max_tokens: 4096
      temperature: 0.7
    
    aws_bedrock:
      enabled: false
      model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
      region: "${AWS_REGION:us-east-1}"
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      max_tokens: 4096
      temperature: 0.7
```

### 2. Environment Variables

Set the required environment variables:

```bash
# For Azure OpenAI
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment-name"

# For AWS Bedrock (if enabled)
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

### 3. Basic Usage

```python
from llm_config_module import LLMManager, LLMProvider

# Initialize the manager (singleton)
manager = LLMManager()

# Get the default LLM provider
llm = manager.get_llm()

# Generate text
response = llm.generate("Hello, how are you today?")
print(response)

# Get provider information
info = llm.get_model_info()
print(f"Using: {info['provider']} - {info['model']}")
```

### 4. DSPY Integration

```python
import dspy
from llm_config_module import LLMManager

# Configure DSPY with the default provider
manager = LLMManager()
manager.configure_dspy()

# Now use DSPY as normal
signature = dspy.Signature("question -> answer")
predictor = dspy.Predict(signature)
result = predictor(question="What is the capital of France?")
```

## Advanced Usage

### Using Specific Providers

```python
from llm_config_module import LLMManager, LLMProvider

manager = LLMManager()

# Use Azure OpenAI specifically
if manager.is_provider_available(LLMProvider.AZURE_OPENAI):
    azure_llm = manager.get_llm(LLMProvider.AZURE_OPENAI)
    response = azure_llm.generate("Your prompt here")

# Use AWS Bedrock specifically
if manager.is_provider_available(LLMProvider.AWS_BEDROCK):
    bedrock_llm = manager.get_llm(LLMProvider.AWS_BEDROCK)
    response = bedrock_llm.generate("Your prompt here")
```

### Custom Configuration File

```python
from llm_config_module import LLMManager

# Use a custom configuration file
manager = LLMManager("/path/to/your/config.yaml")
llm = manager.get_llm()
```

### Provider Information

```python
manager = LLMManager()

# Get available providers
available = manager.get_available_providers()
print(f"Available providers: {list(available.keys())}")

# Get detailed provider information
info = manager.get_provider_info()
print(f"Provider details: {info}")
```

## Configuration Reference

### Environment Variable Substitution

The configuration system supports environment variable substitution using the `${VAR_NAME}` or `${VAR_NAME:default_value}` syntax:

```yaml
endpoint: "${AZURE_OPENAI_ENDPOINT}"  # Required variable
region: "${AWS_REGION:us-east-1}"     # Optional with default
```

### Provider Configuration

#### Azure OpenAI

```yaml
azure_openai:
  enabled: true
  model: "gpt-4o"                    # Model name
  api_version: "2024-02-15-preview"  # API version
  endpoint: "${AZURE_OPENAI_ENDPOINT}"
  api_key: "${AZURE_OPENAI_API_KEY}"
  deployment_name: "${AZURE_OPENAI_DEPLOYMENT_NAME}"
  max_tokens: 4096
  temperature: 0.7
```

#### AWS Bedrock

```yaml
aws_bedrock:
  enabled: true
  model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  region: "${AWS_REGION}"
  access_key_id: "${AWS_ACCESS_KEY_ID}"
  secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
  session_token: "${AWS_SESSION_TOKEN:}"  # Optional
  max_tokens: 4096
  temperature: 0.7
```

## Error Handling

The module provides comprehensive error handling:

```python
from llm_config_module import (
    LLMManager, 
    ConfigurationError, 
    ProviderInitializationError
)

try:
    manager = LLMManager()
    llm = manager.get_llm()
    response = llm.generate("Your prompt")
    
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    
except ProviderInitializationError as e:
    print(f"Provider initialization failed: {e}")
    
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Extending the Module

### Adding a New Provider

1. Create a new provider class inheriting from `BaseLLMProvider`:

```python
from llm_config_module.providers.base import BaseLLMProvider

class MyCustomProvider(BaseLLMProvider):
    @property
    def provider_name(self) -> str:
        return "My Custom Provider"
    
    def get_required_config_fields(self) -> List[str]:
        return ["enabled", "model", "api_key"]
    
    def initialize(self) -> None:
        # Initialize your provider
        pass
    
    def generate(self, prompt: str, **kwargs: Any) -> str:
        # Implement text generation
        pass
    
    def get_dspy_client(self) -> dspy.LM:
        # Return DSPY-compatible client
        pass
```

2. Register the provider with the factory:

```python
from llm_config_module import LLMFactory, LLMProvider

# Extend the enum (this would require modifying the types.py file)
# Then register the provider
LLMFactory.register_provider(LLMProvider.MY_CUSTOM, MyCustomProvider)
```

## Testing

Run the tests to verify everything works:

```bash
uv run pytest tests/test_llm_config_module.py -v
```

## Best Practices

1. **Environment Variables**: Always use environment variables for sensitive information like API keys
2. **Configuration Management**: Keep configuration files in version control, but not the actual secrets
3. **Error Handling**: Always wrap LLM operations in try-catch blocks
4. **Provider Availability**: Check if a provider is available before using it
5. **Singleton Pattern**: The LLMManager is a singleton, so you can safely call `LLMManager()` multiple times

## Troubleshooting

### Common Issues

1. **Configuration not found**: Ensure your `llm_config.yaml` file is in the correct location
2. **Environment variables not set**: Check that all required environment variables are set
3. **Provider initialization fails**: Verify your API credentials and network connectivity
4. **DSPY integration issues**: Ensure DSPY is properly installed and compatible

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Your LLM Config Module code here
```

## API Reference

### LLMManager

- `get_llm(provider: Optional[LLMProvider] = None) -> BaseLLMProvider`
- `get_dspy_client(provider: Optional[LLMProvider] = None) -> dspy.LM`
- `configure_dspy(provider: Optional[LLMProvider] = None) -> None`
- `get_available_providers() -> Dict[LLMProvider, str]`
- `is_provider_available(provider: LLMProvider) -> bool`
- `reload_configuration(config_path: Optional[str] = None) -> None`

### BaseLLMProvider

- `generate(prompt: str, **kwargs: Any) -> str`
- `get_dspy_client() -> dspy.LM`
- `get_model_info() -> Dict[str, Any]`
- `validate_config() -> None`

## License

This module is part of the RAG-Module project. See the main project LICENSE file for details.