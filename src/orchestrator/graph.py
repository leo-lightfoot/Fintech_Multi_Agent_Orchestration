"""LangGraph-based orchestrator graph definition."""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from src.orchestrator.state import (
    OrchestratorState,
    Phase,
    TaskStatus,
    create_initial_state
)
from src.agents.planning.pre_planner import PrePlanner
from src.agents.planning.plan_refiner import PlanRefiner
from src.agents.execution.executor import Executor
from src.agents.validation.critics import CriticAgent
from src.agents.experts.domain_expert import DomainExpert
from src.agents.summarizers.summarizer import Summarizer
from src.agents.responders.responder import Responder
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OrchestrationGraph:
    """LangGraph-based orchestration system."""
    
    def __init__(self):
        """Initialize the orchestration graph."""
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            api_key=settings.openai_api_key
        )
        
        # Initialize agents
        self.pre_planner = PrePlanner(self.llm)
        self.plan_refiner = PlanRefiner(self.llm)
        self.executor = Executor(self.llm)
        self.critic = CriticAgent(self.llm)
        self.domain_expert = DomainExpert(self.llm)
        self.summarizer = Summarizer(self.llm)
        self.responder = Responder(self.llm)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine.
        
        Returns:
            Compiled state graph
        """
        # Create the graph
        workflow = StateGraph(OrchestratorState)
        
        # Add nodes
        workflow.add_node("initialize", self._initialize_node)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("refine_plan", self._refine_plan_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("get_expert_input", self._expert_node)
        workflow.add_node("summarize", self._summarize_node)
        workflow.add_node("respond", self._respond_node)
        workflow.add_node("handle_retry", self._retry_node)
        workflow.add_node("handle_failure", self._failure_node)
        
        # Set entry point
        workflow.set_entry_point("initialize")
        
        # Add edges
        workflow.add_edge("initialize", "plan")
        workflow.add_edge("plan", "refine_plan")
        
        # Conditional: Check if we need expert input
        workflow.add_conditional_edges(
            "refine_plan",
            self._should_get_expert_input,
            {
                "expert": "get_expert_input",
                "execute": "execute"
            }
        )
        
        workflow.add_edge("get_expert_input", "execute")
        workflow.add_edge("execute", "validate")
        
        # Conditional: Validation results
        workflow.add_conditional_edges(
            "validate",
            self._check_validation_result,
            {
                "approved": "summarize",
                "retry": "handle_retry",
                "failed": "handle_failure"
            }
        )
        
        workflow.add_edge("handle_retry", "execute")
        workflow.add_edge("summarize", "respond")
        workflow.add_edge("respond", END)
        workflow.add_edge("handle_failure", END)
        
        # Compile
        return workflow.compile()
    
    # Node implementations
    async def _initialize_node(self, state: OrchestratorState) -> OrchestratorState:
        """Initialize the task."""
        logger.info("node_initialize", task_id=state["task_id"])
        
        state["phase"] = Phase.INIT
        state["status"] = TaskStatus.SUBMITTED
        state["progress"] = 0.05
        
        return state
    
    async def _plan_node(self, state: OrchestratorState) -> OrchestratorState:
        """Generate initial plan."""
        logger.info("node_plan", task_id=state["task_id"])
        
        state["phase"] = Phase.PLANNING
        state["status"] = TaskStatus.PLANNING
        state["progress"] = 0.1
        
        # Generate plan
        plan = await self.pre_planner.create_plan(state["task"], state.get("context"))
        state["execution_plan"] = plan
        
        return state
    
    async def _refine_plan_node(self, state: OrchestratorState) -> OrchestratorState:
        """Refine the execution plan."""
        logger.info("node_refine_plan", task_id=state["task_id"])
        
        state["progress"] = 0.2
        
        # Refine plan
        refined_plan = await self.plan_refiner.refine_plan(
            state["execution_plan"],
            state["task"]
        )
        state["execution_plan"] = refined_plan
        
        return state
    
    async def _execute_node(self, state: OrchestratorState) -> OrchestratorState:
        """Execute the plan."""
        logger.info("node_execute", task_id=state["task_id"])
        
        state["phase"] = Phase.EXECUTION
        state["status"] = TaskStatus.EXECUTING
        state["progress"] = 0.4
        
        # Execute steps
        results = await self.executor.execute_plan(
            state["execution_plan"],
            state.get("context"),
            state["cost_tracking"]
        )
        state["step_results"] = results
        
        state["progress"] = 0.6
        
        return state
    
    async def _validate_node(self, state: OrchestratorState) -> OrchestratorState:
        """Validate execution results."""
        logger.info("node_validate", task_id=state["task_id"])
        
        state["phase"] = Phase.VALIDATION
        state["status"] = TaskStatus.VALIDATING
        state["progress"] = 0.7
        
        # Run critics
        validation = await self.critic.validate(
            state["task"],
            state["step_results"],
            state["execution_plan"]
        )
        state["validation_results"].append(validation)
        
        return state
    
    async def _expert_node(self, state: OrchestratorState) -> OrchestratorState:
        """Get domain expert input."""
        logger.info("node_expert", task_id=state["task_id"])
        
        insights = await self.domain_expert.provide_insights(
            state["task"],
            state.get("context")
        )
        state["expert_insights"].extend(insights)
        
        return state
    
    async def _summarize_node(self, state: OrchestratorState) -> OrchestratorState:
        """Summarize results."""
        logger.info("node_summarize", task_id=state["task_id"])
        
        state["phase"] = Phase.SUMMARIZATION
        state["status"] = TaskStatus.SUMMARIZING
        state["progress"] = 0.85
        
        summary = await self.summarizer.summarize(
            state["task"],
            state["step_results"],
            state["validation_results"]
        )
        state["summary"] = summary
        
        return state
    
    async def _respond_node(self, state: OrchestratorState) -> OrchestratorState:
        """Generate final response."""
        logger.info("node_respond", task_id=state["task_id"])
        
        state["phase"] = Phase.RESPONSE
        state["progress"] = 0.95
        
        response = await self.responder.format_response(
            state["task"],
            state["summary"],
            state["step_results"]
        )
        state["final_response"] = response
        
        state["status"] = TaskStatus.COMPLETED
        state["phase"] = Phase.COMPLETED
        state["progress"] = 1.0
        
        return state
    
    async def _retry_node(self, state: OrchestratorState) -> OrchestratorState:
        """Handle retry logic."""
        logger.info("node_retry", task_id=state["task_id"], retry_count=state["retry_count"])
        
        state["status"] = TaskStatus.RETRYING
        state["retry_count"] += 1
        
        # Reset to execution phase
        state["phase"] = Phase.EXECUTION
        
        return state
    
    async def _failure_node(self, state: OrchestratorState) -> OrchestratorState:
        """Handle failure."""
        logger.error("node_failure", task_id=state["task_id"])
        
        state["status"] = TaskStatus.FAILED
        state["phase"] = Phase.FAILED
        state["progress"] = 1.0
        
        return state
    
    # Conditional edge functions
    def _should_get_expert_input(self, state: OrchestratorState) -> str:
        """Decide if we need domain expert input."""
        # Simple heuristic: complex tasks with multiple steps
        if state["execution_plan"] and len(state["execution_plan"].steps) > 5:
            return "expert"
        return "execute"
    
    def _check_validation_result(self, state: OrchestratorState) -> str:
        """Check validation results and decide next step."""
        if not state["validation_results"]:
            return "failed"
        
        latest_validation = state["validation_results"][-1]
        
        # Check if approved
        if latest_validation.approved:
            return "approved"
        
        # Check retry limit
        if state["retry_count"] >= settings.max_retry_attempts:
            logger.warning(
                "max_retries_exceeded",
                task_id=state["task_id"],
                retry_count=state["retry_count"]
            )
            return "failed"
        
        # Check budget
        if not state["cost_tracking"].check_budget():
            logger.warning(
                "budget_exceeded",
                task_id=state["task_id"],
                cost=state["cost_tracking"].total_cost_usd
            )
            return "failed"
        
        return "retry"
    
    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """Run the orchestration graph.
        
        Args:
            state: Initial state
            
        Returns:
            Final state after processing
        """
        logger.info("graph_started", task_id=state["task_id"])
        
        try:
            # Run the graph
            final_state = await self.graph.ainvoke(state)
            
            logger.info(
                "graph_completed",
                task_id=state["task_id"],
                status=final_state["status"],
                cost=final_state["cost_tracking"].total_cost_usd
            )
            
            return final_state
        
        except Exception as e:
            logger.error(
                "graph_failed",
                task_id=state["task_id"],
                error=str(e),
                exc_info=True
            )
            
            state["status"] = TaskStatus.FAILED
            state["phase"] = Phase.FAILED
            state["errors"].append(str(e))
            
            return state
