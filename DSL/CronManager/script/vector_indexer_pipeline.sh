#!/bin/bash

echo "Starting vector indexer pipeline..."

if [ -z "$signedUrl" ] || [ -z "$clientDataHash" ]; then
  echo "Please set the signedS3Url and clientDataHash environment variables."
  exit 1
fi

PYTHON_SCRIPT="/app/src/vector_indexer/main_indexer.py"

echo "Using signedUrl: $signedUrl"
echo "Using clientDataHash: $clientDataHash"

# Install uv if not found
UV_BIN="/root/.local/bin/uv"
if [ ! -f "$UV_BIN" ]; then
    echo "[UV] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || {
        echo "[ERROR] Failed to install uv"
        exit 1
    }
fi

# Activate Python virtual environment
VENV_PATH="/app/python_virtual_env"
echo "[VENV] Activating virtual environment at: $VENV_PATH"
source "$VENV_PATH/bin/activate" || {
    echo "[ERROR] Failed to activate virtual environment"
    exit 1
}

# Install required packages
echo "[PACKAGES] Installing required packages..."

"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "numpy>=1.21.0,<2.0" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "requests>=2.32.5" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "pydantic>=2.11.7" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "qdrant-client>=1.15.1" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "rank-bm25>=0.2.2" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "tiktoken>=0.11.0" || exit 1
"$UV_BIN" pip install --python "$VENV_PATH/bin/python3" "dvc[s3]>=3.55.2" || exit 1

echo "[PACKAGES] All packages installed successfully"

export PYTHONPATH="/app:/app/src:/app/src/vector_indexer:$PYTHONPATH"

[ ! -f "$PYTHON_SCRIPT" ] && { echo "[ERROR] Python script not found"; exit 1; }

echo "[FOUND] Python script at: $PYTHON_SCRIPT"

# Run vector indexer with signed URL parameter
echo "[STARTING] Vector indexer processing..."
if [ -n "$signedUrl" ]; then
    echo "[SIGNED_URL] Using signed URL for dataset processing"
    python3 "$PYTHON_SCRIPT" --signed-url "$signedUrl"
else
    echo "[NO_URL] Running without signed URL"
    python3 "$PYTHON_SCRIPT"
fi

echo "[COMPLETED] Vector indexer pipeline finished"