"""Stream configuration for timeouts and size limits."""


class StreamConfig:
    """Hardcoded configuration for streaming limits and timeouts."""

    # Timeout Configuration
    MAX_STREAM_DURATION_SECONDS: int = 300  # 5 minutes
    IDLE_TIMEOUT_SECONDS: int = 60  # 1 minute idle timeout

    # Size Limits
    MAX_MESSAGE_LENGTH: int = 10000  # Maximum characters in message
    MAX_PAYLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Token Limits (reuse existing tracking from response_generator)
    MAX_TOKENS_PER_STREAM: int = 4000  # Maximum tokens to generate

    # Concurrency Limits
    MAX_CONCURRENT_STREAMS: int = 100  # System-wide concurrent stream limit
    MAX_STREAMS_PER_USER: int = 5  # Per-user concurrent stream limit

    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = True  # Enable/disable rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 10  # Max requests per user per minute
    RATE_LIMIT_TOKENS_PER_SECOND: int = (
        100  # Max tokens per user per second (burst control)
    )
    RATE_LIMIT_CLEANUP_INTERVAL: int = 300  # Cleanup old entries every 5 minutes
