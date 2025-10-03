"""Embedding Manager for DSPy integration with vault secrets."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import dspy  # type: ignore
import numpy as np  # type: ignore
from loguru import logger
from pydantic import BaseModel

from .vault.vault_client import VaultAgentClient
from .config.loader import ConfigurationLoader
from .exceptions import ConfigurationError


class EmbeddingFailure(BaseModel):
    """Model for tracking embedding failures."""
    
    texts: List[str]
    error_message: str
    timestamp: float
    attempt_count: int
    model_name: str


class EmbeddingManager:
    """Manager for DSPy embedding models with vault integration."""
    
    def __init__(
        self, 
        vault_client: VaultAgentClient, 
        config_loader: ConfigurationLoader
    ) -> None:
        """Initialize embedding manager."""
        self.vault_client = vault_client
        self.config_loader = config_loader
        self.embedders: Dict[str, dspy.Embedder] = {}
        self.failure_log_path = Path("logs/embedding_failures.jsonl")
        self.failure_log_path.parent.mkdir(parents=True, exist_ok=True)
        
    def get_embedder(
        self, 
        model_name: Optional[str] = None, 
        environment: str = "production",
        connection_id: Optional[str] = None
    ) -> dspy.Embedder:
        """Get or create DSPy Embedder instance."""
        # Use same logic as LLM model selection
        actual_model_name = model_name or self._get_default_embedding_model(
            environment, connection_id
        )
        
        cache_key = f"{actual_model_name}_{environment}_{connection_id or 'default'}"
        
        if cache_key in self.embedders:
            return self.embedders[cache_key]
            
        # Load configuration from vault
        config = self._load_embedding_config_from_vault(
            actual_model_name, environment, connection_id
        )
        
        # Create DSPy embedder based on provider
        embedder = self._create_dspy_embedder(config)
        self.embedders[cache_key] = embedder
        
        logger.info(f"Created embedder for model: {actual_model_name}")
        return embedder
        
    def create_embeddings(
        self,
        texts: List[str],
        model_name: Optional[str] = None,
        environment: str = "production", 
        connection_id: Optional[str] = None,
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """Create embeddings using DSPy with error handling."""
        embedder = self.get_embedder(model_name, environment, connection_id)
        actual_model_name = model_name or self._get_default_embedding_model(
            environment, connection_id
        )
        
        try:
            # Process in batches
            all_embeddings = []
            total_tokens = 0
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                logger.info(f"Processing embedding batch {i//batch_size + 1}")
                
                # Use Python's generic exponential backoff
                batch_embeddings = self._create_embeddings_with_retry(
                    embedder, batch_texts, actual_model_name
                )
                all_embeddings.extend(batch_embeddings.tolist())
                
                # Estimate tokens (rough approximation)
                total_tokens += sum(len(text.split()) * 1.3 for text in batch_texts)
                
            return {
                "embeddings": all_embeddings,
                "model_used": actual_model_name,
                "processing_info": {
                    "batch_count": (len(texts) + batch_size - 1) // batch_size,
                    "total_texts": len(texts),
                    "batch_size": batch_size
                },
                "total_tokens": int(total_tokens)
            }
            
        except Exception as e:
            logger.error(f"Embedding creation failed: {e}")
            self._log_embedding_failure(texts, str(e), actual_model_name)
            raise
            
    def _create_embeddings_with_retry(
        self, 
        embedder: dspy.Embedder, 
        texts: List[str],
        model_name: str,
        max_attempts: int = 3
    ) -> np.ndarray:
        """Create embeddings with Python's generic exponential backoff."""
        last_exception: Optional[Exception] = None
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Embedding attempt {attempt + 1}/{max_attempts}")
                return embedder(texts)
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
                
                if attempt < max_attempts - 1:
                    # Exponential backoff: 2^attempt seconds (1, 2, 4, 8...)
                    delay = 2 ** attempt
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    # Final attempt failed, log and raise
                    self._log_embedding_failure(texts, str(e), model_name, attempt + 1)
                    
        if last_exception:
            raise last_exception
        
        # This should never be reached, but makes pyright happy
        raise RuntimeError("Unexpected error in retry logic")
        
    def _get_default_embedding_model(
        self, 
        environment: str, 
        connection_id: Optional[str] = None
    ) -> str:
        """Get default embedding model using same logic as LLM selection."""
        try:
            if environment == "production":
                # For production, get default from environment-specific path
                path = "secret/embeddings/connections/azure_openai/production/default"
            else:
                # For dev/test, use connection_id
                if not connection_id:
                    raise ConfigurationError(
                        f"connection_id required for environment: {environment}"
                    )
                path = f"secret/embeddings/connections/azure_openai/{environment}/{connection_id}/default"
                
            config = self.vault_client.get_secret(path)
            if config is None:
                raise ConfigurationError(f"No default embedding model found at {path}")
            return config.get("model", "text-embedding-3-small")
            
        except Exception as e:
            logger.warning(f"Could not get default embedding model: {e}")
            return "text-embedding-3-small"  # Fallback
            
    def _load_embedding_config_from_vault(
        self,
        model_name: str,
        environment: str, 
        connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Load embedding configuration from vault using same logic as LLM."""
        try:
            # Determine provider from model name
            provider = self._get_provider_from_model(model_name)
            
            if environment == "production":
                path = f"secret/embeddings/connections/{provider}/production/{model_name}"
            else:
                if not connection_id:
                    raise ConfigurationError(
                        f"connection_id required for environment: {environment}"
                    )
                path = f"secret/embeddings/connections/{provider}/{environment}/{connection_id}/{model_name}"
                
            config = self.vault_client.get_secret(path)
            if config is None:
                raise ConfigurationError(f"No embedding configuration found at {path}")
            logger.info(f"Loaded embedding config from vault: {path}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load embedding config: {e}")
            raise ConfigurationError(f"Could not load embedding config: {e}")
            
    def _get_provider_from_model(self, model_name: str) -> str:
        """Determine provider from model name."""
        if "text-embedding" in model_name:
            return "azure_openai"  # Default to Azure OpenAI
        elif "titan" in model_name or "cohere" in model_name:
            return "aws_bedrock"
        else:
            return "openai"
            
    def _create_dspy_embedder(self, config: Dict[str, Any]) -> dspy.Embedder:
        """Create DSPy embedder from vault configuration."""
        try:
            # For Azure OpenAI
            if "azure" in config.get("endpoint", "").lower():
                model_string = f"azure/{config['deployment_name']}"
                # DSPy will use environment variables or we can pass them
                return dspy.Embedder(
                    model=model_string,
                    batch_size=50,  # Small batch size as requested
                    caching=True
                )
            
            # For OpenAI
            elif "openai" in config.get("endpoint", "").lower():
                return dspy.Embedder(
                    model=f"openai/{config['model']}",
                    batch_size=50,
                    caching=True
                )
                
            # For AWS Bedrock
            else:
                return dspy.Embedder(
                    model=f"bedrock/{config['model']}",
                    batch_size=50,
                    caching=True
                )
                
        except Exception as e:
            logger.error(f"Failed to create DSPy embedder: {e}")
            raise ConfigurationError(f"Could not create embedder: {e}")
            
    def _log_embedding_failure(
        self, 
        texts: List[str], 
        error_message: str, 
        model_name: str,
        attempt_count: int = 1
    ) -> None:
        """Log embedding failure to file for later retry."""
        failure = EmbeddingFailure(
            texts=texts,
            error_message=error_message,
            timestamp=time.time(),
            attempt_count=attempt_count,
            model_name=model_name
        )
        
        try:
            with open(self.failure_log_path, 'a', encoding='utf-8') as f:
                f.write(failure.model_dump_json() + '\n')
            logger.info(f"Logged embedding failure to {self.failure_log_path}")
        except Exception as e:
            logger.error(f"Failed to log embedding failure: {e}")
            
    def get_available_models(
        self, 
        environment: str, 
        connection_id: Optional[str] = None
    ) -> List[str]:
        """Get available embedding models from vault."""
        try:
            # For now, return static list of supported models
            # TODO: Implement dynamic model discovery from vault
            _ = environment, connection_id  # Acknowledge parameters for future use
            return [
                "text-embedding-3-small",
                "text-embedding-3-large", 
                "text-embedding-ada-002"
            ]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return ["text-embedding-3-small"]  # Fallback