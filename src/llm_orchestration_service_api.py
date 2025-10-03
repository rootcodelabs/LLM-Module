"""LLM Orchestration Service API - FastAPI application."""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, HTTPException, status, Request
from loguru import logger
import uvicorn

from llm_orchestration_service import LLMOrchestrationService
from models.request_models import (
    OrchestrationRequest, 
    OrchestrationResponse,
    EmbeddingRequest,
    EmbeddingResponse, 
    ContextGenerationRequest,
    ContextGenerationResponse,
    EmbeddingErrorResponse
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting LLM Orchestration Service API")
    try:
        app.state.orchestration_service = LLMOrchestrationService()
        logger.info("LLM Orchestration Service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize LLM Orchestration Service: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down LLM Orchestration Service API")
    # Clean up resources if needed
    if hasattr(app.state, "orchestration_service"):
        app.state.orchestration_service = None


# Create FastAPI application
app = FastAPI(
    title="LLM Orchestration Service API",
    description="API for orchestrating LLM requests with configuration management",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check(request: Request) -> dict[str, str]:
    """Health check endpoint."""
    service_status = (
        "initialized"
        if hasattr(request.app.state, "orchestration_service")
        and request.app.state.orchestration_service is not None
        else "not_initialized"
    )
    return {
        "status": "healthy",
        "service": "llm-orchestration-service",
        "orchestration_service": service_status,
    }


@app.post(
    "/orchestrate",
    response_model=OrchestrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Process LLM orchestration request",
    description="Processes a user message through the LLM orchestration pipeline",
)
def orchestrate_llm_request(
    http_request: Request,
    request: OrchestrationRequest,
) -> OrchestrationResponse:
    """
    Process LLM orchestration request.

    Args:
        http_request: FastAPI Request object for accessing app state
        request: OrchestrationRequest containing user message and context

    Returns:
        OrchestrationResponse: Response with LLM output and status flags

    Raises:
        HTTPException: For processing errors
    """
    try:
        logger.info(f"Received orchestration request for chatId: {request.chatId}")

        # Get the orchestration service from app state
        if not hasattr(http_request.app.state, "orchestration_service"):
            logger.error("Orchestration service not found in app state")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service not initialized",
            )

        orchestration_service = http_request.app.state.orchestration_service
        if orchestration_service is None:
            logger.error("Orchestration service is None")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service not initialized",
            )

        # Process the request
        response = orchestration_service.process_orchestration_request(request)

        logger.info(f"Successfully processed request for chatId: {request.chatId}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred",
        )


@app.post("/embeddings", response_model=EmbeddingResponse, responses={500: {"model": EmbeddingErrorResponse}})
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """
    Create embeddings using DSPy with vault-managed models.
    
    Supports Azure OpenAI, AWS Bedrock, and OpenAI embedding models.
    Includes automatic retry with exponential backoff.
    """
    try:
        logger.info(f"Creating embeddings for {len(request.texts)} texts using model: {request.model_name}")
        
        result = app.state.orchestration_service.create_embeddings(
            texts=request.texts,
            model_name=request.model_name,
            environment="production" if request.connection_id is None else "development",
            connection_id=request.connection_id,
            batch_size=request.batch_size or 50
        )
        
        return EmbeddingResponse(**result)
        
    except Exception as e:
        logger.error(f"Embedding creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e), 
                "failed_texts": request.texts[:5],  # Don't log all texts for privacy
                "retry_after": 30
            }
        )


@app.post("/generate-context", response_model=ContextGenerationResponse)
async def generate_context_with_caching(request: ContextGenerationRequest) -> ContextGenerationResponse:
    """
    Generate contextual descriptions using Anthropic methodology.
    
    Uses exact Anthropic prompt templates and supports structure for
    future prompt caching implementation for cost optimization.
    """
    try:
        logger.info(f"Generating context using model: {request.model}")
        
        result = app.state.orchestration_service.generate_context_with_caching(request)
        
        return ContextGenerationResponse(**result)
        
    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/embedding-models")
async def get_available_embedding_models(
    environment: str = "production",
    connection_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get available embedding models from vault configuration."""
    try:
        # Get available embedding models
        
        result = app.state.orchestration_service.get_available_embedding_models(
            environment=environment, 
            connection_id=connection_id
        )
        return result
        
    except Exception as e:
        logger.error(f"Failed to get embedding models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logger.info("Starting LLM Orchestration Service API server on port 8100")
    uvicorn.run(
        "llm_orchestration_service_api:app",
        host="0.0.0.0",
        port=8100,
        log_level="info",
    )
