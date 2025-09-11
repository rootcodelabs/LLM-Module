"""Run script for LLM Orchestration Service API."""

import sys
import os
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    try:
        import uvicorn  # type: ignore[import-untyped]

        print("Starting LLM Orchestration Service API on port 8100...")
        print(f"Source path: {src_path}")

        # Change to src directory and run
        os.chdir(src_path)

        uvicorn.run(  # type: ignore[attr-defined]
            "llm_orchestration_service_api:app",
            host="0.0.0.0",
            port=8100,
            reload=True,
            log_level="info",
        )

    except ImportError:
        print("uvicorn not installed. Please install dependencies first.")
        print("Commands to run the API:")
        print("1. From project root:")
        print(
            "   cd src && uv run uvicorn llm_orchestration_service_api:app --host 0.0.0.0 --port 8100 --reload"
        )
        print("2. Or use this script:")
        print("   uv run python run_api.py")
    except Exception as e:
        print(f"Error starting server: {e}")
        print("\nAlternative commands to try:")
        print(
            "cd src && uv run uvicorn llm_orchestration_service_api:app --host 0.0.0.0 --port 8100 --reload"
        )
