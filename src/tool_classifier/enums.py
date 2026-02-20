"""Enumerations and constants for tool classifier system."""

from enum import Enum


class WorkflowType(Enum):
    """
    Workflow types representing different query handling strategies.

    The tool classifier uses a layer-wise approach to determine which
    workflow should handle each user query:

    - SERVICE: External service/API calls (Layer 1)
    - CONTEXT: Conversation history or greetings (Layer 2)
    - RAG: Knowledge base retrieval (Layer 3)
    - OOD: Out-of-domain fallback (Layer 4)
    """

    SERVICE = "service"
    CONTEXT = "context"
    RAG = "rag"
    OOD = "ood"


# Layer configuration - defines the order of workflow evaluation
WORKFLOW_LAYER_ORDER = [
    WorkflowType.SERVICE,  # Layer 1: Try service first
    WorkflowType.CONTEXT,  # Layer 2: Then context
    WorkflowType.RAG,  # Layer 3: Then RAG
    WorkflowType.OOD,  # Layer 4: Finally OOD (always succeeds)
]

# Workflow display names for logging
WORKFLOW_DISPLAY_NAMES = {
    WorkflowType.SERVICE: "Service Workflow",
    WorkflowType.CONTEXT: "Context Workflow",
    WorkflowType.RAG: "RAG Workflow",
    WorkflowType.OOD: "Out-of-Domain Workflow",
}
