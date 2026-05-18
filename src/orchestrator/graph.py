"""LangGraph orchestration graph -- supervisor pattern.

Node flow:
    receive -> supervise -> execute -> validate -> respond -> done
                              ^________^  (one retry on validation reject)

Agents are imported lazily so stub files can be added one at a time
without breaking the graph during development.
"""
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END

from src.orchestrator.state import (
    OrchestratorState,
    Phase,
    TaskStatus,
    ValidationResult,
)
from src.audit.trail import AuditTrail, AuditEntry
from src.utils.llm import get_llm
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OrchestrationGraph:
    """Supervisor-pattern LangGraph orchestration system."""

    def __init__(self, redis_store=None):
        self.llm: BaseChatModel = get_llm()
        self.audit = AuditTrail(redis_store)
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("receive", self._receive_node)
        workflow.add_node("supervise", self._supervise_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("respond", self._respond_node)
        workflow.add_node("fail", self._fail_node)

        workflow.set_entry_point("receive")
        workflow.add_edge("receive", "supervise")
        workflow.add_edge("supervise", "execute")
        workflow.add_edge("execute", "validate")

        workflow.add_conditional_edges(
            "validate",
            self._route_after_validation,
            {
                "approved": "respond",
                "retry":    "retry",
                "failed":   "fail",
            },
        )

        workflow.add_node("retry", self._retry_node)
        workflow.add_edge("retry", "execute")
        workflow.add_edge("respond", END)
        workflow.add_edge("fail", END)

        return workflow.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _receive_node(self, state: OrchestratorState) -> OrchestratorState:
        logger.info("node_receive", task_id=state["task_id"])
        state["phase"] = Phase.INIT
        state["status"] = TaskStatus.SUBMITTED
        state["progress"] = 0.05
        return state

    async def _supervise_node(self, state: OrchestratorState) -> OrchestratorState:
        """Classify intent and choose which specialist agents to run."""
        logger.info("node_supervise", task_id=state["task_id"])
        state["phase"] = Phase.SUPERVISING
        state["status"] = TaskStatus.SUPERVISING
        state["progress"] = 0.15

        try:
            from src.agents.supervisor import Supervisor
            supervisor = Supervisor(self.llm)
            decision = await supervisor.decide(state["task"], state.get("context"))
            state["intent"] = decision.intent
            state["agents_selected"] = decision.agents
        except ImportError:
            # Supervisor not yet built -- default routing for development
            logger.warning("supervisor_not_found_using_default_routing")
            state["intent"] = "general"
            state["agents_selected"] = ["data"]

        logger.info(
            "supervision_complete",
            task_id=state["task_id"],
            intent=state["intent"],
            agents=state["agents_selected"],
        )
        return state

    async def _execute_node(self, state: OrchestratorState) -> OrchestratorState:
        """Run each selected agent in sequence, passing results forward."""
        logger.info(
            "node_execute",
            task_id=state["task_id"],
            agents=state["agents_selected"],
            retry=state["retry_count"],
        )
        state["phase"] = Phase.EXECUTING
        state["status"] = TaskStatus.EXECUTING
        state["progress"] = 0.40

        agent_results: dict = {}
        previous_results: dict = dict(state.get("agent_results") or {})

        for agent_name in state["agents_selected"]:
            try:
                agent = self._load_agent(agent_name)
                result = await agent.run(
                    task=state["task"],
                    context=state.get("context"),
                    previous_results=previous_results,
                    validation_feedback=(
                        state["validation_result"].issues
                        if state.get("validation_result") and state["retry_count"] > 0
                        else []
                    ),
                )
                agent_results[agent_name] = {"status": "success", "result": result}
                previous_results[agent_name] = result

                if hasattr(result, "usage_metadata"):
                    self._update_cost(state["cost_tracking"], result.usage_metadata)

                await self.audit.log(AuditEntry(
                    task_id=state["task_id"],
                    session_id=state["session_id"],
                    user_id=state["user_id"],
                    action="agent_executed",
                    agent=agent_name,
                    status="success",
                    result_summary=str(result)[:200],
                    cost_usd=state["cost_tracking"].total_cost_usd,
                ))

            except ImportError:
                logger.warning("agent_not_found_using_stub", agent=agent_name)
                agent_results[agent_name] = {
                    "status": "stub",
                    "result": f"[{agent_name} agent not yet implemented]",
                }
                await self.audit.log(AuditEntry(
                    task_id=state["task_id"],
                    session_id=state["session_id"],
                    user_id=state["user_id"],
                    action="agent_executed",
                    agent=agent_name,
                    status="stub",
                    result_summary=f"{agent_name} not yet implemented",
                ))
            except Exception as exc:
                logger.error("agent_execution_failed", agent=agent_name, error=str(exc))
                agent_results[agent_name] = {"status": "error", "error": str(exc)}
                state["errors"].append(f"{agent_name}: {exc}")
                await self.audit.log(AuditEntry(
                    task_id=state["task_id"],
                    session_id=state["session_id"],
                    user_id=state["user_id"],
                    action="agent_executed",
                    agent=agent_name,
                    status="error",
                    result_summary=str(exc)[:200],
                ))

        state["agent_results"] = agent_results
        state["progress"] = 0.65
        return state

    async def _validate_node(self, state: OrchestratorState) -> OrchestratorState:
        """Single-pass validation of all agent results."""
        logger.info("node_validate", task_id=state["task_id"])
        state["phase"] = Phase.VALIDATING
        state["status"] = TaskStatus.VALIDATING
        state["progress"] = 0.75

        try:
            from src.agents.validator import Validator
            validator = Validator(self.llm)
            result = await validator.validate(
                task=state["task"],
                agent_results=state["agent_results"],
            )
            state["validation_result"] = result
        except ImportError:
            logger.warning("validator_not_found_auto_approving")
            state["validation_result"] = ValidationResult(
                approved=True,
                severity="ok",
                feedback="Auto-approved (validator not yet implemented)",
            )

        return state

    async def _respond_node(self, state: OrchestratorState) -> OrchestratorState:
        """Format agent results into a final markdown response."""
        logger.info("node_respond", task_id=state["task_id"])
        state["phase"] = Phase.RESPONDING
        state["progress"] = 0.90

        try:
            from src.agents.responder import Responder
            responder = Responder(self.llm)
            response = await responder.format_response(
                task=state["task"],
                summary=None,
                results=state["agent_results"],
            )
            state["final_response"] = response
        except ImportError:
            lines = ["## Results\n"]
            for agent, data in state["agent_results"].items():
                result = data.get("result", data.get("error", "no output"))
                lines.append(f"**{agent.title()}**\n\n{result}\n")
            state["final_response"] = "\n".join(lines)

        state["status"] = TaskStatus.COMPLETED
        state["phase"] = Phase.COMPLETED
        state["progress"] = 1.0
        return state

    async def _fail_node(self, state: OrchestratorState) -> OrchestratorState:
        logger.error("node_fail", task_id=state["task_id"], errors=state["errors"])
        state["status"] = TaskStatus.FAILED
        state["phase"] = Phase.FAILED
        state["progress"] = 1.0
        if not state["final_response"]:
            state["final_response"] = (
                "Task could not be completed. "
                f"Errors: {'; '.join(state['errors']) or 'unknown'}"
            )
        return state

    # ------------------------------------------------------------------
    # Conditional routing
    # ------------------------------------------------------------------

    def _route_after_validation(self, state: OrchestratorState) -> str:
        """Read-only routing function -- must not mutate state."""
        result = state.get("validation_result")

        if result and result.approved:
            return "approved"

        if state["retry_count"] >= settings.max_retry_attempts:
            logger.warning("max_retries_reached", task_id=state["task_id"])
            return "failed"

        if not state["cost_tracking"].within_budget():
            logger.warning("budget_exceeded", task_id=state["task_id"])
            return "failed"

        return "retry"

    async def _retry_node(self, state: OrchestratorState) -> OrchestratorState:
        """Increment retry counter and reset status before re-entering execute."""
        state["retry_count"] += 1
        state["status"] = TaskStatus.RETRYING
        logger.info("retrying", task_id=state["task_id"], attempt=state["retry_count"])
        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_agent(self, name: str):
        """Dynamically load a specialist agent by name."""
        if name == "data":
            from src.agents.data import DataAgent
            return DataAgent(self.llm)
        if name == "portfolio":
            from src.agents.portfolio import PortfolioAgent
            return PortfolioAgent(self.llm)
        if name == "risk":
            from src.agents.risk import RiskAgent
            return RiskAgent(self.llm)
        if name == "report":
            from src.agents.reports import ReportAgent
            return ReportAgent(self.llm)
        raise ImportError(f"No agent registered for name: '{name}'")

    def _update_cost(self, tracking, usage_metadata) -> None:
        try:
            tracking.llm_calls += 1
            tracking.tokens_used += (
                getattr(usage_metadata, "input_tokens", 0)
                + getattr(usage_metadata, "output_tokens", 0)
            )
            tracking.total_cost_usd += tracking.tokens_used * 0.000003
        except Exception:
            pass

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """Run the full orchestration graph."""
        logger.info("graph_started", task_id=state["task_id"])
        try:
            final_state = await self.graph.ainvoke(state)
            logger.info("graph_completed", task_id=state["task_id"], status=final_state["status"])
            return final_state
        except Exception as exc:
            logger.error("graph_failed", task_id=state["task_id"], error=str(exc), exc_info=True)
            state["status"] = TaskStatus.FAILED
            state["phase"] = Phase.FAILED
            state["errors"].append(str(exc))
            return state
