import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any
import tiktoken
from loguru import logger

from .chunk_models import Chunk, ChunkMetadata, ChunkingConfig, TokenUsage
from ..embedding_service.embedding_client import EmbeddingClient

class ContextualChunker:
    def __init__(self, config: ChunkingConfig, embedding_client: EmbeddingClient):
        self.config = config
        self.embedding_client = embedding_client
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Token tracking (thread-safe)
        self.token_usage = TokenUsage()
        self.token_lock = threading.Lock()
        
    async def create_contextual_chunks(
        self, 
        document_content: str, 
        metadata_base: Dict[str, Any],
        parallel_threads: int = 5
    ) -> List[Chunk]:
        """Create chunks with contextual information using Anthropic's methodology."""
        
        # 1. Split document into base chunks
        base_chunks = self._split_document(document_content, metadata_base)
        
        logger.info(f"Processing {len(base_chunks)} chunks with {parallel_threads} threads")
        
        # 2. Generate contextual content for each chunk (parallel processing)
        contextual_chunks = []
        
        with ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            futures = [
                executor.submit(self._process_single_chunk, document_content, chunk)
                for chunk in base_chunks
            ]
            
            for future in tqdm(as_completed(futures), total=len(base_chunks), desc="Contextualizing chunks"):
                try:
                    contextual_chunk = await asyncio.wrap_future(future)
                    contextual_chunks.append(contextual_chunk)
                except Exception as e:
                    logger.error(f"Failed to process chunk: {e}")
                    
        # 3. Log token usage and cost savings
        self._log_token_usage()
        
        return contextual_chunks
    
    def _process_single_chunk(self, document_content: str, base_chunk: Chunk) -> Chunk:
        """Process a single chunk to add contextual information."""
        
        # Generate context using LLM orchestration service
        context, usage = self._generate_context(document_content, base_chunk.content)
        
        # Update token tracking (thread-safe)
        with self.token_lock:
            self.token_usage.input_tokens += usage.get('input_tokens', 0)
            self.token_usage.output_tokens += usage.get('output_tokens', 0)
            self.token_usage.cache_creation_tokens += usage.get('cache_creation_tokens', 0)
            self.token_usage.cache_read_tokens += usage.get('cache_read_tokens', 0)
        
        # Create contextual content
        contextual_content = f"{base_chunk.content}\n\n{context}"
        
        # Update metadata
        updated_metadata = base_chunk.metadata.copy()
        updated_metadata.contextualized_content = context
        
        return Chunk(
            id=base_chunk.id,
            content=base_chunk.content,
            contextual_content=contextual_content,
            metadata=updated_metadata
        )
    
    def _generate_context(self, document: str, chunk: str) -> Tuple[str, Dict[str, int]]:
        """Generate contextual description using LLM orchestration service."""
        
        # Prepare prompt with caching structure
        document_prompt = self.config.document_context_prompt.format(doc_content=document)
        chunk_prompt = self.config.chunk_context_prompt.format(chunk_content=chunk)
        
        # Call LLM orchestration service with prompt caching
        response = self.embedding_client.generate_context_with_caching(
            document_prompt=document_prompt,
            chunk_prompt=chunk_prompt,
            model=self.config.context_model,
            max_tokens=self.config.context_max_tokens,
            temperature=self.config.context_temperature,
            use_cache=self.config.use_prompt_caching
        )
        
        return response['context'], response['usage']
    
    def _split_document(self, document_content: str, metadata_base: Dict[str, Any]) -> List[Chunk]:
        """Split document into base chunks."""
        
        if self.config.strategy == ChunkingStrategy.CHARACTER_SPLIT:
            return self._character_split(document_content, metadata_base)
        else:
            raise NotImplementedError(f"Strategy {self.config.strategy} not implemented")
    
    def _character_split(self, text: str, metadata_base: Dict[str, Any]) -> List[Chunk]:
        """Split text by character count with token awareness."""
        
        chunks = []
        tokens = self.tokenizer.encode(text)
        
        for i in range(0, len(tokens), self.config.chunk_size - self.config.chunk_overlap):
            chunk_tokens = tokens[i:i + self.config.chunk_size]
            
            if len(chunk_tokens) < self.config.min_chunk_size and i > 0:
                break
                
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            metadata = ChunkMetadata(
                source_url=metadata_base['source_url'],
                source_file_path=metadata_base['source_file_path'],
                dataset_id=metadata_base['dataset_id'],
                document_id=metadata_base['document_id'],
                chunk_index=len(chunks),
                total_chunks=0,  # Will be updated later
                created_at=datetime.now(),
                original_content=chunk_text
            )
            
            chunk = Chunk(
                id=f"{metadata_base['document_id']}_chunk_{len(chunks)}",
                content=chunk_text,
                contextual_content=chunk_text,  # Will be updated with context
                metadata=metadata
            )
            
            chunks.append(chunk)
        
        # Update total_chunks count
        for chunk in chunks:
            chunk.metadata.total_chunks = len(chunks)
            
        return chunks
    
    def _log_token_usage(self):
        """Log comprehensive token usage and cost savings."""
        
        logger.info("=== Contextual Chunking Token Usage ===")
        logger.info(f"Total input tokens: {self.token_usage.input_tokens}")
        logger.info(f"Total output tokens: {self.token_usage.output_tokens}")
        logger.info(f"Cache creation tokens: {self.token_usage.cache_creation_tokens}")
        logger.info(f"Cache read tokens: {self.token_usage.cache_read_tokens}")
        logger.info(f"Prompt caching savings: {self.token_usage.total_cost_savings_percentage:.2f}%")
        logger.info("Cache read tokens come at 90% discount!")