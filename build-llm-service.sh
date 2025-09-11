#!/bin/bash

# Build and run script for LLM Orchestration Service Docker container

set -e

echo "🐳 Building LLM Orchestration Service Docker container..."

# Build the Docker image
docker build -f Dockerfile.llm_orchestration_service -t llm-orchestration-service:latest .

echo "✅ Docker image built successfully!"

# Check if we should run the container
if [ "$1" = "run" ]; then
    echo "🚀 Starting LLM Orchestration Service container..."
    
    # Stop and remove existing container if it exists
    docker stop llm-orchestration-service 2>/dev/null || true
    docker rm llm-orchestration-service 2>/dev/null || true
    
    # Run the container
    docker run -d \
        --name llm-orchestration-service \
        --network bykstack \
        -p 8100:8100 \
        --env-file .env \
        -e ENVIRONMENT=development \
        -v "$(pwd)/src/llm_config_module/config:/app/src/llm_config_module/config:ro" \
        -v llm_orchestration_logs:/app/logs \
        llm-orchestration-service:latest
    
    echo "✅ LLM Orchestration Service is running!"
    echo "🌐 API available at: http://localhost:8100"
    echo "🔍 Health check: http://localhost:8100/health"
    echo "📊 API docs: http://localhost:8100/docs"
    
    # Show logs
    echo ""
    echo "📋 Container logs (Ctrl+C to stop viewing logs):"
    docker logs -f llm-orchestration-service

elif [ "$1" = "compose" ]; then
    echo "🚀 Starting with Docker Compose..."
    docker-compose up --build llm-orchestration-service

else
    echo ""
    echo "📖 Usage:"
    echo "  $0           - Build the Docker image only"
    echo "  $0 run       - Build and run the container standalone"
    echo "  $0 compose   - Build and run with docker-compose"
    echo ""
    echo "🌐 Once running, the API will be available at:"
    echo "   Health check: http://localhost:8100/health"
    echo "   API docs:     http://localhost:8100/docs"
fi
