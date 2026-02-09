"""
Prompt configuration loader with HTTP client, caching, and retry logic.
"""

import requests
from typing import Optional, Dict, Any
import time
import threading
from loguru import logger


class PromptConfigurationLoader:
    """
    Loads custom prompt configurations from Ruuter endpoint.

    Features:
    - HTTP-based loading via Ruuter
    - 5-minute TTL cache (configurable)
    - 3-attempt retry with exponential backoff
    - Thread-safe caching
    - Graceful degradation with stale cache fallback
    """

    def __init__(
        self,
        ruuter_endpoint: str,
        cache_ttl_seconds: int = 300,
        max_retries: int = 3,
        timeout_seconds: int = 10,
    ) -> None:
        """
        Initialize prompt configuration loader.

        Args:
            ruuter_endpoint: Full URL to Ruuter endpoint
            cache_ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes)
            max_retries: Maximum retry attempts on failure (default: 3)
            timeout_seconds: HTTP request timeout (default: 10)
        """
        self.ruuter_endpoint = ruuter_endpoint
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        # Cache storage
        self._cached_prompt: Optional[str] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_lock = threading.Lock()

        # Statistics for monitoring
        self._cache_hits = 0
        self._cache_misses = 0
        self._load_failures = 0
        self._last_error: Optional[str] = None

        logger.info(
            f"PromptConfigurationLoader initialized: "
            f"endpoint={ruuter_endpoint}, ttl={cache_ttl_seconds}s, retries={max_retries}"
        )

    def get_custom_instructions(self) -> str:
        """
        Get custom prompt configuration (cached or fresh).

        Returns:
            str: Custom instruction text, or empty string if unavailable
        """
        with self._cache_lock:
            # Check cache validity
            if self._is_cache_valid():
                self._cache_hits += 1
                logger.debug(
                    f"Prompt config cache HIT "
                    f"(age: {self._get_cache_age():.1f}s, "
                    f"hits: {self._cache_hits}, misses: {self._cache_misses})"
                )
                return self._cached_prompt or ""

            # Cache miss/expired - load from Ruuter
            self._cache_misses += 1
            logger.info(
                f"Prompt config cache MISS - loading from Ruuter "
                f"(cache age: {self._get_cache_age():.1f}s)"
            )

            try:
                prompt_text = self._load_from_ruuter_with_retry()

                if prompt_text:
                    # Success - update cache
                    self._cached_prompt = prompt_text
                    self._cache_timestamp = time.time()
                    self._last_error = None
                    logger.info(
                        f"Prompt configuration loaded successfully "
                        f"({len(prompt_text)} chars)"
                    )
                    return prompt_text
                else:
                    # No configuration found
                    logger.warning("No prompt configuration found in database")
                    # Return stale cache if available, otherwise empty
                    return self._cached_prompt or ""

            except Exception as e:
                self._load_failures += 1
                self._last_error = str(e)
                logger.error(
                    f"Failed to load prompt configuration: {e} "
                    f"(failures: {self._load_failures})"
                )
                # Fallback to stale cache or empty string
                if self._cached_prompt:
                    logger.warning(
                        f"Using stale cache (age: {self._get_cache_age():.1f}s)"
                    )
                return self._cached_prompt or ""

    def _is_cache_valid(self) -> bool:
        """Check if cache is within TTL window."""
        if self._cached_prompt is None or self._cache_timestamp is None:
            return False

        age = time.time() - self._cache_timestamp
        return age < self.cache_ttl_seconds

    def _get_cache_age(self) -> float:
        """Get cache age in seconds."""
        if self._cache_timestamp is None:
            return float("inf")
        return time.time() - self._cache_timestamp

    def _load_from_ruuter_with_retry(self) -> Optional[str]:
        """
        Load configuration from Ruuter with exponential backoff retry.

        Retry strategy:
        - Attempt 1: 0s wait
        - Attempt 2: 1s wait
        - Attempt 3: 2s wait

        Returns:
            Optional[str]: Prompt text or None if all retries fail
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    f"Calling Ruuter endpoint "
                    f"(attempt {attempt}/{self.max_retries}): {self.ruuter_endpoint}"
                )

                response = requests.post(
                    self.ruuter_endpoint,
                    json={},  # Empty POST body
                    timeout=self.timeout_seconds,
                    headers={"Content-Type": "application/json"},
                )

                # Check HTTP status
                if response.status_code == 200:
                    data = response.json()

                    # DEBUG: Log the actual response structure
                    logger.info(f"Response data type: {type(data)}")
                    logger.info(f"Response data content: {data}")

                    # Handle response format - Ruuter wraps response in 'response' key
                    prompt = ""

                    # Unwrap Ruuter's response wrapper if present
                    if isinstance(data, dict) and "response" in data:
                        logger.info(f"Unwrapping 'response' key")
                        data = data["response"]

                    # Now extract prompt from the unwrapped data
                    if isinstance(data, list) and len(data) > 0:
                        # Array format: [{"id": 1, "prompt": "..."}]
                        logger.info(f"Extracting from list, first element: {data[0]}")
                        prompt = data[0].get("prompt", "").strip()
                    elif isinstance(data, dict):
                        # Dict format: {"id": 1, "prompt": "..."}
                        logger.info(f"Extracting from dict, keys: {list(data.keys())}")
                        prompt = data.get("prompt", "").strip()
                    else:
                        logger.warning(
                            f"Unexpected data type: {type(data)}, value: {data}"
                        )

                    logger.info(
                        f"Extracted prompt length: {len(prompt) if prompt else 0}"
                    )

                    if prompt:
                        logger.info(
                            f"Loaded prompt on attempt {attempt} ({len(prompt)} chars)"
                        )
                        return prompt
                    else:
                        logger.warning(f"Prompt field is empty (attempt {attempt})")
                        return None  # Database has no configuration

                else:
                    logger.warning(
                        f"HTTP {response.status_code} on attempt {attempt}: "
                        f"{response.text[:200]}"
                    )

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Request timeout on attempt {attempt} "
                    f"(timeout: {self.timeout_seconds}s)"
                )

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error on attempt {attempt}: {str(e)[:100]}")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error on attempt {attempt}: {str(e)[:100]}")

            except (ValueError, KeyError) as e:
                logger.error(f"Invalid response format on attempt {attempt}: {e}")

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt}: {e}")

            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                wait_time = 2 ** (attempt - 1)  # 1s, 2s
                logger.debug(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

        # All retries failed
        logger.error(
            f"All {self.max_retries} attempts failed to load prompt configuration"
        )
        return None

    def force_refresh(self) -> bool:
        """
        Force immediate cache refresh.

        Returns:
            bool: True if refresh successful, False otherwise
        """
        logger.info("Forcing prompt configuration cache refresh")
        with self._cache_lock:
            self._cache_timestamp = None  # Invalidate cache

        result = self.get_custom_instructions()
        return bool(result)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        with self._cache_lock:
            return {
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "load_failures": self._load_failures,
                "cache_age_seconds": (
                    round(self._get_cache_age(), 2) if self._is_cache_valid() else None
                ),
                "has_cached_value": self._cached_prompt is not None,
                "cache_valid": self._is_cache_valid(),
                "cached_prompt_length": (
                    len(self._cached_prompt) if self._cached_prompt else 0
                ),
                "last_error": self._last_error,
                "ruuter_endpoint": self.ruuter_endpoint,
                "cache_ttl_seconds": self.cache_ttl_seconds,
            }
