"""Stream timeout utilities for async streaming operations."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.llm_orchestrator_config.exceptions import StreamTimeoutError


@asynccontextmanager
async def stream_timeout(seconds: int) -> AsyncIterator[None]:
    """
    Context manager for stream timeout enforcement.

    Args:
        seconds: Maximum duration in seconds

    Raises:
        StreamTimeoutError: When timeout is exceeded

    Example:
        async with stream_timeout(300):
            async for chunk in stream_generator():
                yield chunk
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError as e:
        raise StreamTimeoutError(
            f"Stream exceeded maximum duration of {seconds} seconds"
        ) from e
