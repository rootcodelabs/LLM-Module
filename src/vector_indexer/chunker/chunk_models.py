from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class ChunkingStrategy(str, Enum):
    CHARACTER_SPLIT = "character_split"
    SEMANTIC_SPLIT = "semantic_split"
    HEADING_SPLIT = "heading_split"

class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    
    @property
    def total_cost_savings_percentage(self) -> float:
        total = self.input_tokens + self.cache_read_tokens + self.cache_creation_tokens
        return (self.cache_read_tokens / total * 100) if total > 0 else 0

class ChunkMetadata(BaseModel):
    source_url: str
    source_file_path: str
    dataset_id: str
    document_id: str
    chunk_index: int
    total_chunks: int
    created_at: datetime
    original_content: str
    contextualized_content: Optional[str] = None

class Chunk(BaseModel):
    id: str
    content: str  # Original content
    contextual_content: str  # Content with context prepended
    metadata: ChunkMetadata
    
class ChunkingConfig(BaseModel):
    chunk_size: int = Field(default=800, description="Target chunk size in tokens")
    chunk_overlap: int = Field(default=100, description="Overlap between chunks")
    min_chunk_size: int = Field(default=100, description="Minimum chunk size")
    strategy: ChunkingStrategy = ChunkingStrategy.CHARACTER_SPLIT
    
    # Anthropic Contextual Retrieval Settings
    context_model: str = Field(default="claude-3-haiku-20240307", description="Model for context generation")
    context_max_tokens: int = Field(default=1000, description="Max tokens for context generation")
    context_temperature: float = Field(default=0.0, description="Temperature for context generation")
    use_prompt_caching: bool = Field(default=True, description="Enable prompt caching for cost optimization")
    
    # Prompt Templates (Based on Anthropic Best Practices)
    document_context_prompt: str = Field(
        default="<document>\n{doc_content}\n</document>"
    )
    
    chunk_context_prompt: str = Field(
        default="""Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else."""
    )