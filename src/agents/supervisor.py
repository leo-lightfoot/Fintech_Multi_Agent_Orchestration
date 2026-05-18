"""Supervisor agent -- classifies intent and selects the agent pipeline.

The supervisor is the first agent called after a task is received.
It reads the task description and outputs a structured routing decision:
  - which intent category the task belongs to
  - which specialist agents should run, in order
  - a short reasoning string for audit/debugging

Available agents (in dependency order):
  data       -- SQL queries, Excel reads, PDF search
  portfolio  -- P&L, attribution, position analysis (needs data first)
  risk       -- limit breaches, exposure, compliance flags (needs data first)
  report     -- formats structured results into a markdown report (runs last)

Routing map:
  data_query         -> [data]
  portfolio_query    -> [data, portfolio]
  risk_compliance    -> [data, risk]
  report_generation  -> [data, report]
  portfolio_report   -> [data, portfolio, report]
  risk_report        -> [data, risk, report]
  full_analysis      -> [data, portfolio, risk, report]
  unknown            -> [data]  (safe fallback)
"""
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a routing supervisor for a fintech solutions team assistant.

Your only job is to read the user's request and decide:
1. Which intent category it belongs to
2. Which specialist agents should handle it, in order

Available intent categories and their agent pipelines:

| Intent              | Agents (in order)              | Use when...                                          |
|---------------------|--------------------------------|------------------------------------------------------|
| data_query          | data                           | Simple data lookup, no analysis needed               |
| portfolio_query     | data, portfolio                | Questions about positions, P&L, NAV, attribution     |
| risk_compliance     | data, risk                     | Limit breaches, exposure, VaR, compliance checks     |
| report_generation   | data, report                   | Formatted report from raw data, no deep analysis     |
| portfolio_report    | data, portfolio, report        | Portfolio analysis presented as a formatted report   |
| risk_report         | data, risk, report             | Risk analysis presented as a formatted report        |
| full_analysis       | data, portfolio, risk, report  | Comprehensive analysis covering both portfolio & risk|
| unknown             | data                           | Anything unclear -- safe fallback                    |

Rules:
- Always include "data" as the first agent -- it fetches the raw data every other agent needs
- Only add "report" if the user explicitly wants a formatted report or document
- Only add "portfolio" if P&L, attribution, positions, or NAV are involved
- Only add "risk" if compliance, limits, exposure, or risk metrics are involved
- Keep the pipeline as short as possible -- do not add agents that aren't needed
- If genuinely unclear, use intent "unknown" with agents ["data"]

Respond with the structured decision only. Do not add explanations outside the structured fields."""


class SupervisorDecision(BaseModel):
    """Structured routing decision from the supervisor."""
    intent: str = Field(
        description=(
            "Intent category. One of: data_query, portfolio_query, risk_compliance, "
            "report_generation, portfolio_report, risk_report, full_analysis, unknown"
        )
    )
    agents: list[str] = Field(
        description=(
            "Ordered list of specialist agents to run. "
            "Valid values: data, portfolio, risk, report"
        )
    )
    reasoning: str = Field(
        description="One sentence explaining why this routing was chosen."
    )


# Valid agent names -- used to sanitize LLM output
VALID_AGENTS = {"data", "portfolio", "risk", "report"}

# Canonical pipelines per intent -- used as fallback if LLM returns wrong agents
INTENT_PIPELINES: dict[str, list[str]] = {
    "data_query":        ["data"],
    "portfolio_query":   ["data", "portfolio"],
    "risk_compliance":   ["data", "risk"],
    "report_generation": ["data", "report"],
    "portfolio_report":  ["data", "portfolio", "report"],
    "risk_report":       ["data", "risk", "report"],
    "full_analysis":     ["data", "portfolio", "risk", "report"],
    "unknown":           ["data"],
}


class Supervisor:
    """Routes a task to the right specialist agent pipeline."""

    def __init__(self, llm: BaseChatModel):
        # Bind structured output so the LLM always returns a SupervisorDecision
        self.llm = llm.with_structured_output(SupervisorDecision)

    async def decide(
        self,
        task: str,
        context: Optional[dict] = None,
    ) -> SupervisorDecision:
        """Classify the task and return a routing decision.

        Args:
            task: The user's task description.
            context: Optional additional context (client ID, date range, etc.)

        Returns:
            SupervisorDecision with intent, agents list, and reasoning.
        """
        logger.info("supervisor_deciding", task_preview=task[:120])

        context_note = ""
        if context:
            context_note = f"\n\nAdditional context provided: {context}"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Task: {task}{context_note}"),
        ]

        try:
            decision: SupervisorDecision = await self.llm.ainvoke(messages)
            decision = self._sanitize(decision)
        except Exception as exc:
            logger.error("supervisor_failed_using_fallback", error=str(exc))
            decision = SupervisorDecision(
                intent="unknown",
                agents=["data"],
                reasoning=f"Supervisor error -- defaulting to data agent. ({exc})",
            )

        logger.info(
            "supervisor_decision",
            intent=decision.intent,
            agents=decision.agents,
            reasoning=decision.reasoning,
        )
        return decision

    def _sanitize(self, decision: SupervisorDecision) -> SupervisorDecision:
        """Guard against the LLM returning invalid agent names or wrong order.

        If the LLM returns an unknown intent, fall back to the canonical pipeline.
        If any agent name is invalid, drop it and use the canonical pipeline instead.
        Always ensure 'data' is first.
        """
        # Fix unknown intent
        if decision.intent not in INTENT_PIPELINES:
            logger.warning("unknown_intent_from_supervisor", intent=decision.intent)
            decision.intent = "unknown"

        # Validate each agent name
        invalid = [a for a in decision.agents if a not in VALID_AGENTS]
        if invalid:
            logger.warning("invalid_agents_from_supervisor", invalid=invalid)
            decision.agents = INTENT_PIPELINES[decision.intent]

        # Always start with data
        if not decision.agents or decision.agents[0] != "data":
            decision.agents = ["data"] + [a for a in decision.agents if a != "data"]

        return decision
