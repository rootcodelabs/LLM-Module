"""Redis async connection manager for session store."""

import os
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger


_redis_client: Optional[aioredis.Redis] = None  # type: ignore[type-arg]


def _build_redis_url() -> str:
    """Build Redis URL from environment variables."""
    host = os.getenv("REDIS_HOST", "redis")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_AUTH", "")
    db = os.getenv("REDIS_SESSION_DB", "1")

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


async def init_redis_client() -> aioredis.Redis:  # type: ignore[type-arg]
    """Initialize the singleton async Redis client.

    Uses db=1 (REDIS_SESSION_DB) to isolate session data from Langfuse (db=0).
    Should be called once during FastAPI lifespan startup.
    """
    global _redis_client

    url = _build_redis_url()
    _redis_client = aioredis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
    )

    # Verify connectivity
    await _redis_client.ping()
    logger.info(
        "Redis session store connected (db={})", os.getenv("REDIS_SESSION_DB", "1")
    )
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client connection pool gracefully."""
    global _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis session store connection closed")


def get_redis_client() -> Optional[aioredis.Redis]:  # type: ignore[type-arg]
    """Return the initialized Redis client, or None if not initialized."""
    return _redis_client


async def check_redis_health() -> str:
    """Check Redis connectivity for the health endpoint.

    Returns:
        "connected" if Redis is reachable, "disconnected" otherwise.
    """
    client = get_redis_client()
    if client is None:
        return "not_configured"
    try:
        await client.ping()
        return "connected"
    except Exception:
        return "disconnected"
