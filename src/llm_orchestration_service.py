"""LLM Orchestration Service - Business logic for LLM orchestration."""

from typing import Optional, List, Dict, Union, Any
import json
from loguru import logger

from llm_orchestrator_config.llm_manager import LLMManager
from models.request_models import (
    OrchestrationRequest,
    OrchestrationResponse,
    ConversationItem,
    PromptRefinerOutput,
    ContextGenerationRequest,
)
from prompt_refine_manager.prompt_refiner import PromptRefinerAgent
from vector_indexer.chunk_config import ChunkConfig
from vector_indexer.hybrid_retrieval import HybridRetriever
from src.response_generator.response_generate import ResponseGeneratorAgent
from src.llm_orchestrator_config.llm_cochestrator_constants import (
    OUT_OF_SCOPE_MESSAGE,
    TECHNICAL_ISSUE_MESSAGE,
)


class LLMOrchestrationService:
    """Stateless service class for handling LLM orchestration business logic."""

    def __init__(self) -> None:
        """Initialize the orchestration service with new managers."""
        # Initialize managers for new functionality
        from llm_orchestrator_config.embedding_manager import EmbeddingManager
        from llm_orchestrator_config.context_manager import ContextGenerationManager
        from llm_orchestrator_config.llm_manager import LLMManager
        from llm_orchestrator_config.vault.vault_client import VaultAgentClient
        from llm_orchestrator_config.config.loader import ConfigurationLoader
        
        # Initialize vault client and config loader (reusing existing patterns)
        self.vault_client = VaultAgentClient()
        self.config_loader = ConfigurationLoader()
        self.llm_manager = LLMManager()
        
        # Initialize new managers
        self.embedding_manager = EmbeddingManager(self.vault_client, self.config_loader)
        self.context_manager = ContextGenerationManager(self.llm_manager)

    def process_orchestration_request(
        self, request: OrchestrationRequest
    ) -> OrchestrationResponse:
        """
        Process an orchestration request and return response.

        Args:
            request: The orchestration request containing user message and context

        Returns:
            OrchestrationResponse: Response with LLM output and status flags

        Raises:
            Exception: For any processing errors
        """
        try:
            logger.info(
                f"Processing orchestration request for chatId: {request.chatId}, "
                f"authorId: {request.authorId}, environment: {request.environment}"
            )

            # Initialize LLM Manager with configuration (per-request)
            llm_manager = self._initialize_llm_manager(
                environment=request.environment, connection_id=request.connection_id
            )

            # Initialize Hybrid Retriever (per-request)
            hybrid_retriever: Optional[HybridRetriever] = None
            try:
                hybrid_retriever = self._initialize_hybrid_retriever()
                logger.info("Hybrid Retriever initialization successful")
            except Exception as retriever_error:
                logger.warning(
                    f"Hybrid Retriever initialization failed: {str(retriever_error)}"
                )
                logger.warning("Continuing without chunk retrieval capabilities")
                hybrid_retriever = None

            # Initialize Response Generator
            response_generator: Optional[ResponseGeneratorAgent] = None
            try:
                response_generator = self._initialize_response_generator(llm_manager)
                logger.info("Response Generator initialization successful")
            except Exception as generator_error:
                logger.warning(
                    f"Response Generator initialization failed: {str(generator_error)}"
                )
                # Do not attempt any other LLM path; we'll return the technical issue message later.
                response_generator = None

            # Step 2: Refine user prompt using loaded configuration
            refined_output = self._refine_user_prompt(
                llm_manager=llm_manager,
                original_message=request.message,
                conversation_history=request.conversationHistory,
            )

            # Step 3: Retrieve relevant chunks using hybrid retrieval (optional)
            relevant_chunks: List[Dict[str, Union[str, float, Dict[str, Any]]]] = []
            if hybrid_retriever is not None:
                try:
                    relevant_chunks = self._retrieve_relevant_chunks(
                        hybrid_retriever=hybrid_retriever, refined_output=refined_output
                    )
                    logger.info(f"Successfully retrieved {len(relevant_chunks)} chunks")
                except Exception as retrieval_error:
                    logger.warning(f"Chunk retrieval failed: {str(retrieval_error)}")
                    logger.warning(
                        "Returning out-of-scope message due to retrieval failure"
                    )
                    # Return out-of-scope response immediately
                    return OrchestrationResponse(
                        chatId=request.chatId,
                        llmServiceActive=True,
                        questionOutOfLLMScope=True,
                        inputGuardFailed=False,
                        content=OUT_OF_SCOPE_MESSAGE,
                    )
            else:
                logger.info("Hybrid Retriever not available, skipping chunk retrieval")

            # Step 4: Generate response with ResponseGenerator only (no extra LLM fallbacks)
            try:
                response = self._generate_rag_response(
                    llm_manager=llm_manager,
                    request=request,
                    refined_output=refined_output,
                    relevant_chunks=relevant_chunks,
                    response_generator=response_generator,
                )
                logger.info(
                    f"Successfully generated RAG response for chatId: {request.chatId}"
                )
                return response

            except Exception as response_error:
                logger.error(f"RAG response generation failed: {str(response_error)}")
                # Standardized technical issue; no second LLM call, no citations
                return OrchestrationResponse(
                    chatId=request.chatId,
                    llmServiceActive=False,
                    questionOutOfLLMScope=False,
                    inputGuardFailed=False,
                    content=TECHNICAL_ISSUE_MESSAGE,
                )

        except Exception as e:
            logger.error(
                f"Error processing orchestration request for chatId: {request.chatId}, "
                f"error: {str(e)}"
            )
            # Technical issue at top-level
            return OrchestrationResponse(
                chatId=request.chatId,
                llmServiceActive=False,
                questionOutOfLLMScope=False,
                inputGuardFailed=False,
                content=TECHNICAL_ISSUE_MESSAGE,
            )

    def _initialize_llm_manager(
        self, environment: str, connection_id: Optional[str]
    ) -> LLMManager:
        """
        Initialize LLM Manager with proper configuration.

        Args:
            environment: Environment context (production/test/development)
            connection_id: Optional connection identifier

        Returns:
            LLMManager: Initialized LLM manager instance
        """
        try:
            logger.info(f"Initializing LLM Manager for environment: {environment}")

            llm_manager = LLMManager(
                environment=environment, connection_id=connection_id
            )

            llm_manager.ensure_global_config()

            logger.info("LLM Manager initialized successfully")
            return llm_manager

        except Exception as e:
            logger.error(f"Failed to initialize LLM Manager: {str(e)}")
            raise

    def _refine_user_prompt(
        self,
        llm_manager: LLMManager,
        original_message: str,
        conversation_history: List[ConversationItem],
    ) -> PromptRefinerOutput:
        """
        Refine user prompt using loaded LLM configuration and log all variants.

        Args:
            llm_manager: The LLM manager instance to use
            original_message: The original user message to refine
            conversation_history: Previous conversation context

        Returns:
            PromptRefinerOutput: The refined prompt output containing original and refined questions

        Raises:
            ValueError: When LLM Manager is not initialized
            ValidationError: When prompt refinement output validation fails
            Exception: For other prompt refinement failures
        """
        logger.info("Starting prompt refinement process")

        try:
            # Convert conversation history to DSPy format
            history: List[Dict[str, str]] = []
            for item in conversation_history:
                role = "assistant" if item.authorRole == "bot" else item.authorRole
                history.append({"role": role, "content": item.message})

            # Create prompt refiner using the same LLM manager instance
            refiner = PromptRefinerAgent(llm_manager=llm_manager)

            # Generate structured prompt refinement output
            refinement_result = refiner.forward_structured(
                history=history, question=original_message
            )

            # Validate the output schema using Pydantic - this will raise ValidationError if invalid
            try:
                validated_output = PromptRefinerOutput(**refinement_result)
            except Exception as validation_error:
                logger.error(
                    f"Prompt refinement output validation failed: {str(validation_error)}"
                )
                logger.error(f"Invalid refinement result: {refinement_result}")
                raise ValueError(
                    f"Prompt refinement validation failed: {str(validation_error)}"
                ) from validation_error

            output_json = validated_output.model_dump()
            logger.info(
                f"Prompt refinement output: {json.dumps(output_json, indent=2)}"
            )

            logger.info("Prompt refinement completed successfully")
            return validated_output

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Prompt refinement failed: {str(e)}")
            logger.error(f"Failed to refine message: {original_message}")
            raise RuntimeError(f"Prompt refinement process failed: {str(e)}") from e

    def _initialize_hybrid_retriever(self) -> HybridRetriever:
        """
        Initialize hybrid retriever for document retrieval.

        Returns:
            HybridRetriever: Initialized hybrid retriever instance
        """
        logger.info("Initializing hybrid retriever")

        try:
            # Initialize vector store with chunk config
            chunk_config = ChunkConfig()
            hybrid_retriever = HybridRetriever(cfg=chunk_config)

            logger.info("Hybrid retriever initialized successfully")
            return hybrid_retriever

        except Exception as e:
            logger.error(f"Failed to initialize hybrid retriever: {str(e)}")
            raise

    def _initialize_response_generator(
        self, llm_manager: LLMManager
    ) -> ResponseGeneratorAgent:
        """
        Initialize Response Generator with the provided LLM manager.

        Args:
            llm_manager: The LLM manager instance to use for response generation

        Returns:
            ResponseGeneratorAgent: Initialized response generator instance
        """
        logger.info("Initializing response generator")

        try:
            # Set up DSPy configuration for the response generator
            with llm_manager.use_task_local():
                response_generator = ResponseGeneratorAgent()

            logger.info("Response generator initialized successfully")
            return response_generator

        except Exception as e:
            logger.error(f"Failed to initialize response generator: {str(e)}")
            raise

    def _retrieve_relevant_chunks(
        self, hybrid_retriever: HybridRetriever, refined_output: PromptRefinerOutput
    ) -> List[Dict[str, Union[str, float, Dict[str, Any]]]]:
        """
        Retrieve relevant chunks using hybrid retrieval approach.

        Args:
            hybrid_retriever: The hybrid retriever instance to use
            refined_output: The output from prompt refinement containing original and refined questions

        Returns:
            List of relevant document chunks with scores and metadata

        Raises:
            ValueError: When Hybrid Retriever is not initialized
            Exception: For retrieval errors
        """
        logger.info("Starting chunk retrieval process")

        try:
            # Use the hybrid retriever to get relevant chunks
            relevant_chunks = hybrid_retriever.retrieve(
                original_question=refined_output.original_question,
                refined_questions=refined_output.refined_questions,
                topk_dense=40,
                topk_bm25=40,
                fused_cap=120,
                final_topn=12,
            )

            logger.info(f"Retrieved {len(relevant_chunks)} relevant chunks")

            # Log first 3 for debugging (safe formatting for score)
            for i, chunk in enumerate(relevant_chunks[:3]):
                score = chunk.get("score", 0.0)
                try:
                    score_str = (
                        f"{float(score):.4f}"
                        if isinstance(score, (int, float))
                        else str(score)
                    )
                except Exception:
                    score_str = str(score)
                logger.info(
                    f"Chunk {i + 1}: ID={chunk.get('id', 'N/A')}, Score={score_str}"
                )

            return relevant_chunks

        except Exception as e:
            logger.error(f"Chunk retrieval failed: {str(e)}")
            logger.error(
                f"Failed to retrieve chunks for question: {refined_output.original_question}"
            )
            raise RuntimeError(f"Chunk retrieval process failed: {str(e)}") from e

    def _generate_rag_response(
        self,
        llm_manager: LLMManager,
        request: OrchestrationRequest,
        refined_output: PromptRefinerOutput,
        relevant_chunks: List[Dict[str, Union[str, float, Dict[str, Any]]]],
        response_generator: Optional[ResponseGeneratorAgent] = None,
    ) -> OrchestrationResponse:
        """
        Generate response using retrieved chunks and ResponseGeneratorAgent only.
        No secondary LLM paths; no citations appended.
        """
        logger.info("Starting RAG response generation")

        # If response generator is not available -> standardized technical issue (no extra LLM calls)
        if response_generator is None:
            logger.warning(
                "Response generator unavailable – returning technical issue message."
            )
            return OrchestrationResponse(
                chatId=request.chatId,
                llmServiceActive=False,
                questionOutOfLLMScope=False,
                inputGuardFailed=False,
                content=TECHNICAL_ISSUE_MESSAGE,
            )

        try:
            with llm_manager.use_task_local():
                generator_result = response_generator.forward(
                    question=refined_output.original_question,
                    chunks=relevant_chunks or [],
                    max_blocks=10,
                )

            answer = (generator_result.get("answer") or "").strip()
            question_out_of_scope = bool(
                generator_result.get("questionOutOfLLMScope", False)
            )

            if question_out_of_scope:
                logger.info("Question determined out-of-scope – sending fixed message.")
                return OrchestrationResponse(
                    chatId=request.chatId,
                    llmServiceActive=True,  # service OK; insufficient context
                    questionOutOfLLMScope=True,
                    inputGuardFailed=False,
                    content=OUT_OF_SCOPE_MESSAGE,
                )

            # In-scope: return the answer as-is (NO citations)
            logger.info("Returning in-scope answer without citations.")
            return OrchestrationResponse(
                chatId=request.chatId,
                llmServiceActive=True,
                questionOutOfLLMScope=False,
                inputGuardFailed=False,
                content=answer,
            )

        except Exception as e:
            logger.error(f"RAG Response generation failed: {str(e)}")
            # Standardized technical issue; no second LLM call, no citations
            return OrchestrationResponse(
                chatId=request.chatId,
                llmServiceActive=False,
                questionOutOfLLMScope=False,
                inputGuardFailed=False,
                content=TECHNICAL_ISSUE_MESSAGE,
            )

    def create_embeddings(
        self, 
        texts: List[str], 
        model_name: Optional[str] = None, 
        environment: str = "production",
        connection_id: Optional[str] = None, 
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """Create embeddings using DSPy Embedder with vault configuration."""
        logger.info(f"Creating embeddings for {len(texts)} texts")
        
        try:
            return self.embedding_manager.create_embeddings(
                texts=texts,
                model_name=model_name,
                environment=environment,
                connection_id=connection_id,
                batch_size=batch_size
            )
        except Exception as e:
            logger.error(f"Embedding creation failed: {e}")
            raise

    def generate_context_with_caching(
        self, 
        request: ContextGenerationRequest
    ) -> Dict[str, Any]:
        """Generate context using Anthropic methodology with caching structure."""
        logger.info("Generating context with Anthropic methodology")
        
        try:
            return self.context_manager.generate_context_with_caching(request)
        except Exception as e:
            logger.error(f"Context generation failed: {e}")
            raise

    def get_available_embedding_models(
        self, 
        environment: str = "production", 
        connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get available embedding models from vault configuration."""
        try:
            available_models = self.embedding_manager.get_available_models(
                environment, connection_id
            )
            # Get default model through public interface
            try:
                default_model = self.embedding_manager.get_embedder(
                    model_name=None, environment=environment, connection_id=connection_id
                )
                default_model = "text-embedding-3-small"  # Fallback for now
            except Exception:
                default_model = "text-embedding-3-small"
            
            return {
                "available_models": available_models,
                "default_model": default_model
            }
        except Exception as e:
            logger.error(f"Failed to get embedding models: {e}")
            raise