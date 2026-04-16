"""Pydantic models for API tool session state."""

from typing import Any
from pydantic import BaseModel, Field


class APIToolSession(BaseModel):
    """Persisted session state for the API Tool Calling agentic loop.

    Keyed by chat_id in Redis with a sliding 30-minute TTL.
    """

    chat_id: str = Field(..., description="Unique conversation identifier")
    state: str = Field(
        ...,
        description="Current state of the agentic loop (e.g. 'collecting_params', 'ready', 'completed')",
    )
    selected_endpoint: dict[str, Any] | None = Field(
        default=None,
        description="The API endpoint selected for this conversation",
    )
    collected_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters collected from the user so far",
    )
    turn_count: int = Field(
        default=0,
        ge=0,
        description="Number of turns elapsed in the agentic loop",
    )
    max_turns: int = Field(
        default=5,
        ge=1,
        description="Maximum turns allowed before the session is abandoned",
    )
    awaiting_continuation: bool = Field(
        default=False,
        description=(
            "True when the loop has reached the continuation threshold and is waiting "
            "for the user to decide whether to continue collecting parameters or exit "
            "to the RAG workflow."
        ),
    )
