"""Rate limiter for streaming endpoints with sliding window and token bucket algorithms."""

import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple, Optional, Any
from threading import Lock

from loguru import logger
from pydantic import BaseModel, Field, ConfigDict

from src.llm_orchestrator_config.stream_config import StreamConfig


class RateLimitResult(BaseModel):
    """Result of rate limit check."""

    model_config = ConfigDict(frozen=True)  # Make immutable like dataclass

    allowed: bool
    retry_after: Optional[int] = Field(
        default=None, description="Seconds to wait before retrying"
    )
    limit_type: Optional[str] = Field(
        default=None, description="'requests' or 'tokens'"
    )
    current_usage: Optional[int] = Field(
        default=None, description="Current usage count"
    )
    limit: Optional[int] = Field(default=None, description="Maximum allowed limit")


class RateLimiter:
    """
    In-memory rate limiter with sliding window (requests/minute) and token bucket (tokens/second).

    Features:
    - Sliding window for request rate limiting (e.g., 10 requests per minute)
    - Token bucket for burst control (e.g., 100 tokens per second)
    - Per-user tracking with authorId
    - Automatic cleanup of old entries to prevent memory leaks
    - Thread-safe operations

    Usage:
        rate_limiter = RateLimiter(
            requests_per_minute=10,
            tokens_per_second=100
        )

        result = rate_limiter.check_rate_limit(
            author_id="user-123",
            estimated_tokens=50
        )

        if not result.allowed:
            # Return 429 with retry_after
            pass
    """

    def __init__(
        self,
        requests_per_minute: int = StreamConfig.RATE_LIMIT_REQUESTS_PER_MINUTE,
        tokens_per_second: int = StreamConfig.RATE_LIMIT_TOKENS_PER_SECOND,
        cleanup_interval: int = StreamConfig.RATE_LIMIT_CLEANUP_INTERVAL,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per user per minute (sliding window)
            tokens_per_second: Maximum tokens per user per second (token bucket)
            cleanup_interval: Seconds between automatic cleanup of old entries
        """
        self.requests_per_minute = requests_per_minute
        self.tokens_per_second = tokens_per_second
        self.cleanup_interval = cleanup_interval

        # Sliding window: Track request timestamps per user
        # Format: {author_id: deque([timestamp1, timestamp2, ...])}
        self._request_history: Dict[str, Deque[float]] = defaultdict(deque)

        # Token bucket: Track token consumption per user
        # Format: {author_id: (last_refill_time, available_tokens)}
        self._token_buckets: Dict[str, Tuple[float, float]] = {}

        # Thread safety
        self._lock = Lock()

        # Cleanup tracking
        self._last_cleanup = time.time()

        logger.info(
            f"RateLimiter initialized - "
            f"requests_per_minute: {requests_per_minute}, "
            f"tokens_per_second: {tokens_per_second}"
        )

    def check_rate_limit(
        self,
        author_id: str,
        estimated_tokens: int = 0,
    ) -> RateLimitResult:
        """
        Check if request is allowed under rate limits.

        Args:
            author_id: User identifier for rate limiting
            estimated_tokens: Estimated tokens for this request (for token bucket)

        Returns:
            RateLimitResult with allowed status and retry information
        """
        with self._lock:
            current_time = time.time()

            # Periodic cleanup to prevent memory leaks
            if current_time - self._last_cleanup > self.cleanup_interval:
                self._cleanup_old_entries(current_time)

            # Check 1: Sliding window (requests per minute)
            request_result = self._check_request_limit(author_id, current_time)
            if not request_result.allowed:
                return request_result

            # Check 2: Token bucket (tokens per second)
            if estimated_tokens > 0:
                token_result = self._check_token_limit(
                    author_id, estimated_tokens, current_time
                )
                if not token_result.allowed:
                    return token_result

            # Both checks passed - record the request
            self._record_request(author_id, current_time, estimated_tokens)

            return RateLimitResult(allowed=True)

    def _check_request_limit(
        self,
        author_id: str,
        current_time: float,
    ) -> RateLimitResult:
        """
        Check sliding window request limit.

        Args:
            author_id: User identifier
            current_time: Current timestamp

        Returns:
            RateLimitResult for request limit check
        """
        request_history = self._request_history[author_id]
        window_start = current_time - 60  # 60 seconds = 1 minute

        # Remove requests outside the sliding window
        while request_history and request_history[0] < window_start:
            request_history.popleft()

        # Check if limit exceeded
        current_requests = len(request_history)
        if current_requests >= self.requests_per_minute:
            # Calculate retry_after based on oldest request in window
            oldest_request = request_history[0]
            retry_after = int(oldest_request + 60 - current_time) + 1

            logger.warning(
                f"Rate limit exceeded for {author_id} - "
                f"requests: {current_requests}/{self.requests_per_minute} "
                f"(retry after {retry_after}s)"
            )

            return RateLimitResult(
                allowed=False,
                retry_after=retry_after,
                limit_type="requests",
                current_usage=current_requests,
                limit=self.requests_per_minute,
            )

        return RateLimitResult(allowed=True)

    def _check_token_limit(
        self,
        author_id: str,
        estimated_tokens: int,
        current_time: float,
    ) -> RateLimitResult:
        """
        Check token bucket limit.

        Token bucket algorithm:
        - Bucket refills at constant rate (tokens_per_second)
        - Burst allowed up to bucket capacity
        - Request denied if insufficient tokens

        Args:
            author_id: User identifier
            estimated_tokens: Tokens needed for this request
            current_time: Current timestamp

        Returns:
            RateLimitResult for token limit check
        """
        bucket_capacity = self.tokens_per_second

        # Get or initialize bucket for user
        if author_id not in self._token_buckets:
            # New user - start with full bucket
            self._token_buckets[author_id] = (current_time, bucket_capacity)

        last_refill, available_tokens = self._token_buckets[author_id]

        # Refill tokens based on time elapsed
        time_elapsed = current_time - last_refill
        refill_amount = time_elapsed * self.tokens_per_second
        available_tokens = min(bucket_capacity, available_tokens + refill_amount)

        # Check if enough tokens available
        if available_tokens < estimated_tokens:
            # Calculate time needed to refill enough tokens
            tokens_needed = estimated_tokens - available_tokens
            retry_after = int(tokens_needed / self.tokens_per_second) + 1

            logger.warning(
                f"Token rate limit exceeded for {author_id} - "
                f"needed: {estimated_tokens}, available: {available_tokens:.0f} "
                f"(retry after {retry_after}s)"
            )

            return RateLimitResult(
                allowed=False,
                retry_after=retry_after,
                limit_type="tokens",
                current_usage=int(bucket_capacity - available_tokens),
                limit=self.tokens_per_second,
            )

        return RateLimitResult(allowed=True)

    def _record_request(
        self,
        author_id: str,
        current_time: float,
        tokens_consumed: int,
    ) -> None:
        """
        Record a successful request.

        Args:
            author_id: User identifier
            current_time: Current timestamp
            tokens_consumed: Tokens consumed by this request
        """
        # Record request timestamp for sliding window
        self._request_history[author_id].append(current_time)

        # Deduct tokens from bucket
        if tokens_consumed > 0 and author_id in self._token_buckets:
            last_refill, available_tokens = self._token_buckets[author_id]

            # Refill before deducting
            time_elapsed = current_time - last_refill
            refill_amount = time_elapsed * self.tokens_per_second
            available_tokens = min(
                self.tokens_per_second, available_tokens + refill_amount
            )

            # Deduct tokens
            available_tokens -= tokens_consumed
            self._token_buckets[author_id] = (current_time, available_tokens)

    def _cleanup_old_entries(self, current_time: float) -> None:
        """
        Clean up old entries to prevent memory leaks.

        Args:
            current_time: Current timestamp
        """
        logger.debug("Running rate limiter cleanup...")

        # Clean up request history (remove entries older than 1 minute)
        window_start = current_time - 60
        users_to_remove: list[str] = []

        for author_id, request_history in self._request_history.items():
            # Remove old requests
            while request_history and request_history[0] < window_start:
                request_history.popleft()

            # Remove empty histories
            if not request_history:
                users_to_remove.append(author_id)

        for author_id in users_to_remove:
            del self._request_history[author_id]

        # Clean up token buckets (remove entries inactive for 5 minutes)
        inactive_threshold = current_time - 300
        buckets_to_remove: list[str] = []

        for author_id, (last_refill, _) in self._token_buckets.items():
            if last_refill < inactive_threshold:
                buckets_to_remove.append(author_id)

        for author_id in buckets_to_remove:
            del self._token_buckets[author_id]

        self._last_cleanup = current_time

        if users_to_remove or buckets_to_remove:
            logger.debug(
                f"Cleaned up {len(users_to_remove)} request histories and "
                f"{len(buckets_to_remove)} token buckets"
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with stats about current usage
        """
        with self._lock:
            return {
                "total_users_tracked": len(self._request_history),
                "total_token_buckets": len(self._token_buckets),
                "requests_per_minute_limit": self.requests_per_minute,
                "tokens_per_second_limit": self.tokens_per_second,
                "last_cleanup": self._last_cleanup,
            }

    def reset_user(self, author_id: str) -> None:
        """
        Reset rate limits for a specific user (useful for testing).

        Args:
            author_id: User identifier to reset
        """
        with self._lock:
            if author_id in self._request_history:
                del self._request_history[author_id]
            if author_id in self._token_buckets:
                del self._token_buckets[author_id]

            logger.info(f"Reset rate limits for user: {author_id}")
