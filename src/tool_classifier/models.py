"""Data models for tool classifier system."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from tool_classifier.enums import AgenticLoopStatus, WorkflowType


class ClassificationResult(BaseModel):
    """
    Result of query classification by the tool classifier.

    This model encapsulates the decision of which workflow should handle
    a user query, along with confidence score and metadata.

    Attributes:
        workflow: The workflow type that should handle this query
        confidence: Confidence score (0.0-1.0) for this classification
        metadata: Workflow-specific data (e.g., service_id, intent, entities)
        reasoning: Human-readable explanation of why this workflow was chosen
    """

    workflow: WorkflowType = Field(
        ..., description="Which workflow should handle this query"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this classification",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Workflow-specific data passed to executor"
    )
    reasoning: Optional[str] = Field(
        default=None, description="Explanation of classification decision"
    )


class ServiceWorkflowMetadata(BaseModel):
    """
    Metadata specific to Service Workflow execution.

    TODO: Will be populated by service discovery logic with:
    - service_id: Identified service to call
    - intent: Detected user intent
    - entities: Extracted parameters for service call
    - confidence: Intent detection confidence
    """

    service_id: Optional[str] = Field(
        default=None, description="ID of the service to execute"
    )
    intent: Optional[str] = Field(
        default=None, description="Detected user intent/service name"
    )
    entities: Optional[Dict[str, Any]] = Field(
        default=None, description="Extracted entities/parameters"
    )


class ContextWorkflowMetadata(BaseModel):
    """
    Metadata specific to Context Workflow execution.

    TODO: Will be populated by context analysis logic with:
    - is_greeting: Whether query is a greeting
    - greeting_type: Type of greeting (hello, goodbye, thanks, etc.)
    - can_answer_from_history: Whether conversation history has answer
    - relevant_history_indices: Indices of relevant history items
    """

    is_greeting: bool = Field(
        default=False, description="Whether this is a greeting/conversational query"
    )
    greeting_type: Optional[str] = Field(
        default=None, description="Type of greeting: hello, goodbye, thanks, casual"
    )
    can_answer_from_history: bool = Field(
        default=False, description="Whether conversation history can answer this"
    )


@dataclass
class AgenticLoopResult:
    """
    Result returned by AgenticLoop.run_turn() after processing one conversation turn.

    Attributes:
        status: Outcome of this turn — completed, needs_input, max_turns_reached,
            or awaiting_continuation_decision.
        collected_params: All parameters collected so far (prior turns + this turn merged).
        clarifying_question: Natural-language question to show the user when status is
            NEEDS_INPUT or AWAITING_CONTINUATION_DECISION. Empty string for other statuses.
        turn_count: Updated turn counter (input turn_count + 1).
    """

    status: AgenticLoopStatus
    collected_params: Dict[str, Any]
    clarifying_question: str
    turn_count: int
