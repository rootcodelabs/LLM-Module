"""Basic query validation for empty/meaningless inputs.

This module provides lightweight, rule-based validation to reject syntactically
invalid queries before they reach expensive LLM-based processing stages.

Validation checks (all syntactic, NO semantic):
- Empty or whitespace-only messages
- Messages containing only special characters/punctuation
- Messages with too few meaningful characters (< 2)
- Messages with only repetitive characters (e.g., "aaaa", "????")

Out of scope for this module:
- Semantic validation (greetings, chitchat, intent detection)
- Language quality checks
- Content policy checks (handled by guardrails)
"""

from typing import Optional
from pydantic import BaseModel


class QueryValidationResult(BaseModel):
    """Result of basic query validation.

    Attributes:
        is_valid: True if query passes all validation checks
        rejection_reason: Optional reason code if validation fails
                         (empty, special_chars_only, too_short, repetitive)
    """

    is_valid: bool
    rejection_reason: Optional[str] = None


def validate_query_basic(query: str) -> QueryValidationResult:
    """
    Validate query for basic syntactic issues (NOT semantic).

    This is a fast, rule-based check that runs before expensive operations
    like guardrails or prompt refinement. It only catches obvious syntactic
    issues, not semantic problems.

    Args:
        query: User's input message to validate

    Returns:
        QueryValidationResult with is_valid flag and optional rejection_reason

    Examples:
        >>> validate_query_basic("How to apply for benefits?")
        QueryValidationResult(is_valid=True, rejection_reason=None)

        >>> validate_query_basic("...")
        QueryValidationResult(is_valid=False, rejection_reason='special_chars_only')

        >>> validate_query_basic("")
        QueryValidationResult(is_valid=False, rejection_reason='empty')

        >>> validate_query_basic("????")
        QueryValidationResult(is_valid=False, rejection_reason='repetitive')
    """
    # Trim whitespace
    query = query.strip()

    # Check 1: Empty query
    if not query:
        return QueryValidationResult(is_valid=False, rejection_reason="empty")

    # Check 2: Only special characters/punctuation
    # These are common non-meaningful characters that don't form queries
    special_chars = ".,?!;:…-_()[]{}@#$%^&*+=~`|\\/<>\"' \t\n"
    if all(c in special_chars for c in query):
        return QueryValidationResult(
            is_valid=False, rejection_reason="special_chars_only"
        )

    # Check 3: Too short (< 2 meaningful characters)
    # Extract alphanumeric characters (letters + numbers)
    meaningful_chars = "".join(c for c in query if c.isalnum())
    if len(meaningful_chars) < 2:
        return QueryValidationResult(is_valid=False, rejection_reason="too_short")

    # Check 4: Only repetitive characters (e.g., "aaaa", "????")
    # If all meaningful characters are the same, it's likely spam/noise
    if len(set(meaningful_chars)) == 1:
        return QueryValidationResult(is_valid=False, rejection_reason="repetitive")

    # Passed all checks - query is syntactically valid
    return QueryValidationResult(is_valid=True)
