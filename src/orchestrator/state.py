"""State definitions for the LangGraph orchestrator."""
from typing import TypedDict, Annotated, Sequence, Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class Phase(str, Enum):
    """Phases of task processing."""
    INIT = "init"
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    SUMMARIZATION = "summarization"
    RESPONSE = "response"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Task status values."""
    SUBMITTED = "submitted"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class AgentType(str, Enum):
    """Types of agents in the system."""
    PRE_PLANNER = "pre_planner"
    PLAN_REFINER = "plan_refiner"
    EXECUTOR = "executor"
    DATA_WRITER = "data_writer"
    CODE_EXECUTOR = "code_executor"
    CRITIC = "critic"
    DOMAIN_EXPERT = "domain_expert"
    SUMMARIZER = "summarizer"
    RESPONDER = "responder"


class PlanStep(BaseModel):
    """A single step in the execution plan."""
    step_id: str
    description: str
    agent_type: AgentType
    dependencies: List[str] = Field(default_factory=list)
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0


class ExecutionPlan(BaseModel):
    """Complete execution plan with DAG."""
    steps: List[PlanStep] = Field(default_factory=list)
    dag: Dict[str, List[str]] = Field(default_factory=dict)  # step_id -> dependencies
    created_at: datetime = Field(default_factory=datetime.utcnow)
    refined: bool = False


class ValidationResult(BaseModel):
    """Result from critic validation."""
    approved: bool
    critic_level: int
    feedback: str
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class CostTracking(BaseModel):
    """Track costs throughout execution."""
    total_cost_usd: float = 0.0
    llm_calls: int = 0
    tokens_used: int = 0
    budget_limit_usd: float
    
    def check_budget(self) -> bool:
        """Check if we're within budget."""
        return self.total_cost_usd < self.budget_limit_usd


class OrchestratorState(TypedDict):
    """Complete state for the LangGraph orchestrator.
    
    This state is passed through all nodes in the graph.
    """
    # Task identifiers
    task_id: str
    session_id: str
    user_id: str
    
    # Task details
    task: str
    context: Optional[Dict[str, Any]]
    
    # Current status
    phase: Phase
    status: TaskStatus
    progress: float  # 0.0 to 1.0
    
    # Planning data
    execution_plan: Optional[ExecutionPlan]
    
    # Execution results
    step_results: Dict[str, Any]  # step_id -> result
    
    # Validation
    validation_results: List[ValidationResult]
    retry_count: int
    
    # Expert knowledge
    expert_insights: List[str]
    
    # Summarized context
    summary: Optional[str]
    
    # Final output
    final_response: Optional[str]
    
    # Error tracking
    errors: List[str]
    
    # Cost and performance
    cost_tracking: CostTracking
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Metadata
    metadata: Dict[str, Any]


def create_initial_state(
    task_id: str,
    session_id: str,
    user_id: str,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    budget_limit_usd: float = 10.0
) -> OrchestratorState:
    """Create the initial state for a new task.
    
    Args:
        task_id: Unique task identifier
        session_id: Session identifier
        user_id: User identifier
        task: Task description
        context: Additional context
        budget_limit_usd: Budget limit for this task
        
    Returns:
        Initial orchestrator state
    """
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
        execution_plan=None,
        step_results={},
        validation_results=[],
        retry_count=0,
        expert_insights=[],
        summary=None,
        final_response=None,
        errors=[],
        cost_tracking=CostTracking(budget_limit_usd=budget_limit_usd),
        created_at=now,
        updated_at=now,
        metadata={}
    )
