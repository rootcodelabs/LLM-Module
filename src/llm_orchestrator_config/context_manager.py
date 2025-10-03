"""Context Generation Manager using Anthropic methodology."""

from typing import Any, Dict, Optional

from loguru import logger

from .llm_manager import LLMManager
from ..models.request_models import ContextGenerationRequest


class ContextGenerationManager:
    """Manager for context generation with Anthropic methodology."""
    
    # Anthropic's exact prompt templates from their research
    DOCUMENT_CONTEXT_PROMPT = """<document>
{doc_content}
</document>"""
    
    CHUNK_CONTEXT_PROMPT = """Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else."""
    
    def __init__(self, llm_manager: LLMManager) -> None:
        """Initialize context generation manager."""
        self.llm_manager = llm_manager
        # Cache structure prepared for future prompt caching implementation
        self._cache: Dict[str, Any] = {}
        
    def generate_context_with_caching(
        self, 
        request: ContextGenerationRequest
    ) -> Dict[str, Any]:
        """Generate context using Anthropic methodology with caching structure."""
        try:
            logger.info(f"Generating context using model: {request.model}")
            
            # Prepare the full prompt using Anthropic's format
            full_prompt = self._prepare_anthropic_prompt(
                request.document_prompt, 
                request.chunk_prompt
            )
            
            # For now, call LLM directly (caching structure ready for future)
            # TODO: Implement actual prompt caching when ready
            response = self._call_llm_for_context(
                prompt=full_prompt,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                connection_id=request.connection_id
            )
            
            # Extract and format response
            usage_metrics = self._extract_usage_metrics(response)
            
            return {
                "context": response.content.strip(),
                "usage": usage_metrics["usage"],
                "cache_performance": usage_metrics["cache_performance"],
                "model_used": response.model
            }
            
        except Exception as e:
            logger.error(f"Context generation failed: {e}")
            raise
            
    def _prepare_anthropic_prompt(
        self, 
        document_prompt: str, 
        chunk_prompt: str
    ) -> str:
        """Prepare prompt in Anthropic's exact format."""
        # Format document section
        document_section = self.DOCUMENT_CONTEXT_PROMPT.format(
            doc_content=document_prompt
        )
        
        # Format chunk section  
        chunk_section = self.CHUNK_CONTEXT_PROMPT.format(
            chunk_content=chunk_prompt
        )
        
        # Combine using Anthropic's methodology
        return f"{document_section}\n\n{chunk_section}"
        
    def _call_llm_for_context(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        connection_id: Optional[str] = None
    ) -> Any:
        """Call LLM for context generation."""
        # Acknowledge unused parameters for future implementation
        _ = max_tokens, temperature, connection_id
        
        # Configure DSPy for this call
        self.llm_manager.ensure_global_config()
        
        # Use DSPy to make the LLM call
        import dspy  # type: ignore
        
        # Create a simple DSPy signature for context generation
        class ContextGeneration(dspy.Signature):  # type: ignore
            """Generate succinct context for a chunk within a document."""
            prompt = dspy.InputField()  # type: ignore
            context = dspy.OutputField()  # type: ignore
        
        # Use DSPy Predict to generate context
        context_generator = dspy.Predict(ContextGeneration)  # type: ignore
        result = context_generator(prompt=prompt)
        
        # Return a response object with the expected structure
        class MockResponse:
            def __init__(self, content: str, model: str):
                self.content = content
                self.model = model
                self.usage = MockUsage(content, prompt)
        
        class MockUsage:
            def __init__(self, content: str, prompt: str):
                self.input_tokens = int(len(prompt.split()) * 1.3)  # Rough estimate
                self.output_tokens = int(len(content.split()) * 1.3)
        
        return MockResponse(str(result.context), model)  # type: ignore
        
    def _extract_usage_metrics(self, response: Any) -> Dict[str, Any]:
        """Extract token usage and caching metrics."""
        # Extract basic usage info
        usage = getattr(response, 'usage', {})
        
        # Prepare cache performance metrics (ready for future implementation)
        cache_performance = {
            "cache_hit": False,  # TODO: Implement when prompt caching is added
            "cache_tokens_read": 0,
            "cache_tokens_written": 0,
            "cache_savings_percentage": 0.0
        }
        
        # Format usage metrics
        formatted_usage = {
            "input_tokens": getattr(usage, 'input_tokens', 0),
            "output_tokens": getattr(usage, 'output_tokens', 0),
            "total_tokens": getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)
        }
        
        return {
            "usage": formatted_usage,
            "cache_performance": cache_performance
        }