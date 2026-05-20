"""State definitions for the LangGraph orchestrator."""
from typing import TypedDict, Optional, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class Phase(str, Enum):
    INIT = "init"
    SUPERVISING = "supervising"
    EXECUTING = "executing"
    VALIDATING = "validating"
    RESPONDING = "responding"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    SUPERVISING = "supervising"
    EXECUTING = "executing"
    VALIDATING = "validating"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationResult(BaseModel):
    """Result from the single-pass validator."""
    approved: bool
    severity: str = "ok"          # ok | warn | reject
    issues: list[str] = Field(default_factory=list)
    feedback: str = ""


class CostTracking(BaseModel):
    """Track LLM costs throughout execution."""
    total_cost_usd: float = 0.0
    llm_calls: int = 0
    tokens_used: int = 0
    budget_limit_usd: float = 10.0

    def within_budget(self) -> bool:
        return self.total_cost_usd < self.budget_limit_usd


class OrchestratorState(TypedDict):
    """Complete state passed through every node in the graph."""

    # Identifiers
    task_id: str
    session_id: str
    user_id: str

    # Input
    task: str
    context: Optional[dict[str, Any]]

    # Lifecycle
    phase: Phase
    status: TaskStatus
    progress: float          # 0.0 -> 1.0

    # Supervisor outputs
    intent: Optional[str]                  # classified intent label
    agents_selected: list[str]             # e.g. ["data", "risk", "report"]

    # Execution outputs
    agent_results: dict[str, Any]          # agent_name -> result dict

    # Validation
    validation_result: Optional[ValidationResult]
    retry_count: int

    # Final output
    final_response: Optional[str]

    # Error tracking
    errors: list[str]

    # Cost
    cost_tracking: CostTracking

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Flexible metadata
    metadata: dict[str, Any]


def create_initial_state(
    task_id: str,
    session_id: str,
    user_id: str,
    task: str,
    context: Optional[dict[str, Any]] = None,
    budget_limit_usd: float = 10.0,
) -> OrchestratorState:
    """Create a clean initial state for a new task."""
    now = datetime.utcnow()
    return OrchestratorState(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        task=task,
        context=context,
        phase=Phase.INIT,
        status=TaskStatus.SUBMITTED,
        progress=0.0,
        intent=None,
        agents_selected=[],
        agent_results={},
        validation_result=None,
        retry_count=0,
        final_response=None,
        errors=[],
        cost_tracking=CostTracking(budget_limit_usd=budget_limit_usd),
        created_at=now,
        updated_at=now,
        metadata={},
    )
