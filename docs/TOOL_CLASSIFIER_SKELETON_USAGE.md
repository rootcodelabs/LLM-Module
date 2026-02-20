# Tool Classifier Skeleton - Usage Guide

**Version**: 1.0  
**Date**: February 17, 2026  
**Status**: Skeleton Implementation  

---

## Overview

This skeleton implements the **framework** for a multi-workflow routing system based on the [TOOL_CLASSIFIER_EXTENSION_SPEC.md](./TOOL_CLASSIFIER_EXTENSION_SPEC.md) specification.

### Current Status

 **Implemented (Skeleton)**:
- Abstract base classes and interfaces
- Workflow executor skeletons (Service, Context, RAG, OOD)
- Tool classifier with classification and routing logic
- Feature flags for safe deployment
- Integration into LLMOrchestrationService

 **Not Implemented (Separate Tasks)**:
- Service discovery logic (Layer 1)
- Context analysis logic (Layer 2)
- Actual LLM calls in workflows
- Output guardrails integration for new workflows
- Database schema changes

### Current Behavior

When `TOOL_CLASSIFIER_ENABLED=false` (default):
-  System works exactly as before (RAG-only pipeline)
-  No changes to existing functionality

When `TOOL_CLASSIFIER_ENABLED=true`:
-  Classifier routes queries (currently always to RAG)
-  Service and Context workflows return `None` (fallback to RAG)
-  RAG workflow wraps existing pipeline
-  All queries ultimately handled by RAG

---

## Architecture

### Layer-Wise Workflow Routing

```
User Query
    ↓
Input Guardrails
    ↓
Tool Classifier
    ↓
┌────────────────┐
│ Classification │
└────────┬───────┘
         ↓
   ┌─────┴──────┐
   │  Routing   │
   └─────┬──────┘
         ↓
    ╔═══════════════════════════════════╗
    ║   Layer 1: Service Workflow       ║ → (returns None - not implemented)
    ╚═══════════════════════════════════╝
         ↓ (fallback)
    ╔═══════════════════════════════════╗
    ║   Layer 2: Context Workflow       ║ → (returns None - not implemented)
    ╚═══════════════════════════════════╝
         ↓ (fallback)
    ╔═══════════════════════════════════╗
    ║   Layer 3: RAG Workflow           ║ →  Handles query (existing pipeline)
    ╚═══════════════════════════════════╝
         ↓
    Response to User
```

### Component Structure

```
src/tool_classifier/
├── __init__.py               # Module exports
├── enums.py                  # WorkflowType enum
├── models.py                 # ClassificationResult models
├── base_workflow.py          # Abstract BaseWorkflow class
├── classifier.py             # Main ToolClassifier
└── workflows/
    ├── __init__.py
    ├── service_workflow.py   # Layer 1 (skeleton)
    ├── context_workflow.py   # Layer 2 (skeleton)
    ├── rag_workflow.py       # Layer 3 (complete)
    └── ood_workflow.py       # Layer 4 (skeleton)
```

### Abstract Base Class Pattern

The system uses **BaseWorkflow** as an abstract base class to ensure all workflows follow the same contract.

#### How It Works

1. **BaseWorkflow defines the contract**:
   - Every workflow MUST implement two methods: `execute_async()` and `execute_streaming()`
   - Both methods return `Optional[...]` to support the fallback pattern (return `None` → next layer)
   - Python's `@abstractmethod` decorator enforces this at instantiation time

2. **All workflows inherit from BaseWorkflow**:
   - ServiceWorkflowExecutor extends BaseWorkflow → implements both methods
   - ContextWorkflowExecutor extends BaseWorkflow → implements both methods
   - RAGWorkflowExecutor extends BaseWorkflow → implements both methods
   - OODWorkflowExecutor extends BaseWorkflow → implements both methods

3. **Classifier treats all workflows uniformly**:
   - The `ToolClassifier.route_to_workflow()` method doesn't need to know which specific workflow it's calling
   - It just calls `workflow.execute_async()` or `workflow.execute_streaming()`
   - This is **polymorphism** - same interface, different behavior

4. **Benefits**:
   - **Consistency**: All workflows have the same interface
   - **Enforcement**: Can't create a workflow without implementing required methods
   - **Flexibility**: Easy to add new workflows - just extend BaseWorkflow
   - **Testability**: Each workflow can be tested independently
   - **Fallback Pattern**: `Optional` return type enables layer chaining

#### Example Flow

```
ToolClassifier needs to execute a workflow
    ↓
Gets workflow object (could be Service, Context, RAG, or OOD)
    ↓
Calls workflow.execute_async(request, context)
    ↓
BaseWorkflow contract guarantees this method exists
    ↓
Each workflow implements its own logic
    ↓
Returns OrchestrationResponse or None (fallback to next layer)
```

The abstract class is like a **blueprint** that says: "Any workflow in this system MUST be able to do these two things: execute normally and execute with streaming. I don't care *how* you do it, but you must provide these capabilities."

---

## Feature Flags

### Environment Variables

```bash
# Master switch (default: false for safe deployment)
TOOL_CLASSIFIER_ENABLED=false

# Individual workflow toggles (only apply when classifier enabled)
SERVICE_WORKFLOW_ENABLED=true
CONTEXT_WORKFLOW_ENABLED=true
```

### Configuration Class

```python
from src.llm_orchestrator_config.feature_flags import FeatureFlags

# Check if classifier is enabled
if FeatureFlags.TOOL_CLASSIFIER_ENABLED:
    # Use tool classifier
    pass

# Check specific workflow
if FeatureFlags.is_workflow_enabled("service"):
    # Service workflow logic
    pass

# Log current configuration
FeatureFlags.log_configuration()
```

---

## How It Works

### 1. Non-Streaming Endpoint (`/orchestrate`)

#### Current Flow (TOOL_CLASSIFIER_ENABLED=false)

```python
POST /orchestrate
    ↓
LLMOrchestrationService.process_orchestration_request()
    ↓
Initialize components (LLM, guardrails, retriever, generator)
    ↓
Execute RAG pipeline
    ↓
Return OrchestrationResponse
```

#### With Classifier (TOOL_CLASSIFIER_ENABLED=true)

```python
POST /orchestrate
    ↓
LLMOrchestrationService.process_orchestration_request()
    ↓
Initialize components
    ↓
Tool Classifier Integration:
    1. Initialize ToolClassifier (if first time)
    2. Classify query → ClassificationResult
       - Currently always returns: WorkflowType.RAG
    3. Route to workflow:
       - ServiceWorkflow.execute_async() → returns None
       - ContextWorkflow.execute_async() → returns None
       - RAGWorkflow.execute_async() → returns response 
    ↓
Return OrchestrationResponse
```

### 2. Streaming Endpoint (`/orchestrate/stream`)

#### Current Flow (TOOL_CLASSIFIER_ENABLED=false)

```python
POST /orchestrate/stream
    ↓
LLMOrchestrationService.stream_orchestration_response()
    ↓
Initialize components
    ↓
Check input guardrails
    ↓
Refine prompt → Retrieve chunks → Stream through NeMo
    ↓
Yield SSE strings
```

#### With Classifier (TOOL_CLASSIFIER_ENABLED=true)

```python
POST /orchestrate/stream
    ↓
LLMOrchestrationService.stream_orchestration_response()
    ↓
Initialize components
    ↓
Check input guardrails
    ↓
Tool Classifier Integration:
    1. Initialize ToolClassifier (if first time)
    2. Classify query → ClassificationResult
    3. Route to streaming workflow:
       - ServiceWorkflow.execute_streaming() → returns None
       - ContextWorkflow.execute_streaming() → returns None
       - RAGWorkflow.execute_streaming() → yields SSE 
    ↓
Yield SSE strings
```

### 3. Test Endpoint (`/orchestrate/test`)

Works identically to `/orchestrate`:
- Converts `TestOrchestrationRequest` → `OrchestrationRequest`
- Routes through classifier (if enabled)
- Converts response back to `TestOrchestrationResponse`

---

## Code Examples

### Using the Classification System

```python
from src.tool_classifier import ToolClassifier, WorkflowType, ClassificationResult

# Initialize classifier
classifier = ToolClassifier(
    llm_manager=llm_manager,
    orchestration_service=service,
)

# Classify a query
classification = await classifier.classify(
    query="Hello, how are you?",
    conversation_history=[],
    language="en",
)

# Check result
print(classification.workflow)  # WorkflowType.RAG (in skeleton)
print(classification.confidence)  # 1.0
print(classification.reasoning)  # "Default to RAG workflow..."

# Route to workflow
response = await classifier.route_to_workflow(
    classification=classification,
    request=request,
    is_streaming=False,
)
```

### Implementing a Workflow (Example)

```python
from src.tool_classifier.base_workflow import BaseWorkflow
from models.request_models import OrchestrationRequest, OrchestrationResponse

class MyCustomWorkflow(BaseWorkflow):
    """Custom workflow implementation."""
    
    async def execute_async(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[OrchestrationResponse]:
        """Handle query in non-streaming mode."""
        
        # Check if this workflow can handle the query
        can_handle = await self._check_if_applicable(request.message)
        
        if not can_handle:
            # Return None to trigger fallback to next layer
            return None
        
        # Execute workflow logic
        result = await self._process_query(request.message)
        
        # Validate with output guardrails (TODO)
        # is_safe = await guardrails.check_output_async(result)
        # if not is_safe:
        #     return None or violation_response
        
        # Return response
        return OrchestrationResponse(
            chatId=request.chatId,
            llmServiceActive=True,
            questionOutOfLLMScope=False,
            inputGuardFailed=False,
            content=result,
        )
    
    async def execute_streaming(
        self,
        request: OrchestrationRequest,
        context: Dict[str, Any],
    ) -> Optional[AsyncIterator[str]]:
        """Handle query in streaming mode."""
        
        # Check if applicable
        can_handle = await self._check_if_applicable(request.message)
        
        if not can_handle:
            return None  # Fallback
        
        # Get complete result
        result = await self._process_query(request.message)
        
        # Validate with guardrails (TODO)
        # is_safe = await guardrails.check_output_async(result)
        # if not is_safe:
        #     yield format_sse(chatId, VIOLATION_MESSAGE)
        #     yield format_sse(chatId, "END")
        #     return
        
        # Stream result token-by-token
        async def stream_result():
            for chunk in self._split_into_tokens(result):
                yield self._format_sse(request.chatId, chunk)
                await asyncio.sleep(0.01)
            yield self._format_sse(request.chatId, "END")
        
        return stream_result()
```

---

## Deployment Strategy

### Phase 1: Testing (Current State)

```bash
# Keep classifier disabled
TOOL_CLASSIFIER_ENABLED=false
```

**Result**: System works exactly as before (RAG-only)

### Phase 2: Enable Classifier (No Impact)

```bash
# Enable classifier (but workflows not implemented)
TOOL_CLASSIFIER_ENABLED=true
SERVICE_WORKFLOW_ENABLED=true
CONTEXT_WORKFLOW_ENABLED=true
```

**Result**: 
- Classifier runs but always routes to RAG
- Service/Context return `None` → fallback to RAG
- Functionally identical to Phase 1
- Validates integration works

### Phase 3: Implement Service Workflow

1. Implement service discovery logic (separate task)
2. Deploy with `SERVICE_WORKFLOW_ENABLED=true`
3. Monitor service routing behavior
4. Rollback flag if issues occur

### Phase 4: Implement Context Workflow

1. Implement context analysis logic (separate task)
2. Deploy with `CONTEXT_WORKFLOW_ENABLED=true`
3. Monitor greeting/context detection
4. Rollback flag if issues occur

### Phase 5: Production

All workflows operational, full layer-wise routing active.

---

## Extending the System

### Adding a New Workflow

1. **Create Workflow Executor**:

```python
# src/tool_classifier/workflows/custom_workflow.py

from src.tool_classifier.base_workflow import BaseWorkflow

class CustomWorkflowExecutor(BaseWorkflow):
    """Your custom workflow."""
    
    async def execute_async(self, request, context):
        # Implement logic
        pass
    
    async def execute_streaming(self, request, context):
        # Implement streaming logic
        pass
```

2. **Register in Classifier**:

```python
# src/tool_classifier/enums.py

class WorkflowType(Enum):
    SERVICE = "service"
    CONTEXT = "context"
    RAG = "rag"
    CUSTOM = "custom"  # Add new type
    OOD = "ood"

# Update layer order
WORKFLOW_LAYER_ORDER = [
    WorkflowType.SERVICE,
    WorkflowType.CONTEXT,
    WorkflowType.CUSTOM,  # Add to chain
    WorkflowType.RAG,
    WorkflowType.OOD,
]
```

3. **Initialize in ToolClassifier**:

```python
# src/tool_classifier/classifier.py

def __init__(self, ...):
    # ... existing workflows ...
    self.custom_workflow = CustomWorkflowExecutor(...)
```

4. **Add Feature Flag**:

```python
# src/llm_orchestrator_config/feature_flags.py

CUSTOM_WORKFLOW_ENABLED = (
    os.getenv("CUSTOM_WORKFLOW_ENABLED", "true").lower() == "true"
)
```

---

## Key Concepts

### 1. None Return Pattern

Workflows return `None` when they cannot handle a query:

```python
if not can_handle:
    return None  # Triggers fallback to next layer
```

This enables the fallback chain: Service → Context → RAG → OOD

### 2. Validation-First Streaming

For Service and Context workflows (complete responses):

```python
# 1. Get complete response
response = await call_service(...)

# 2. Validate BEFORE streaming
is_safe = await guardrails.check_output_async(response)

if not is_safe:
    yield format_sse(chatId, VIOLATION_MESSAGE)
    yield format_sse(chatId, "END")
    return

# 3. Stream validated response
for chunk in split_into_tokens(response):
    yield format_sse(chatId, chunk)
yield format_sse(chatId, "END")
```

### 3. Two Execution Methods

Every workflow implements both:
- `execute_async()` → For `/orchestrate` (returns complete response)
- `execute_streaming()` → For `/orchestrate/stream` (yields SSE strings)

---

## Summary

This skeleton provides:

 **Complete framework** for multi-workflow routing  
 **Safe deployment** with feature flags  
 **Extensible architecture** using OOP patterns  
 **Backward compatibility** (disabled by default)  
 **Clear contracts** via abstract base classes  
 **Documentation** for implementation tasks  

The system is ready for workflow implementation in separate, independent tasks.

---
