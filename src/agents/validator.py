"""Validator -- single-pass structured output check of all agent results.

Checks completeness, accuracy, and safety. Returns a ValidationResult
(defined in state.py) that the graph uses to decide approve / retry / fail.

One retry is allowed. On retry the validator's issues are fed back to
the execute node so agents can address them.
"""
import json
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.orchestrator.state import ValidationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an output validator for a fintech multi-agent system.

You review the combined output of all specialist agents and decide whether
the result is good enough to return to the user.

Checks to perform:
1. Completeness -- does the output address what the user asked?
2. Consistency -- do figures match across agents (e.g. NAV in portfolio matches nav_history)?
3. Safety -- no PII (names, account numbers, email addresses) in the output
4. No hallucination -- every number cited must appear in the source data
5. Breaches surfaced -- if limit_rules data shows breached=1, the output must mention it

Severity rules:
- "ok"     : approved, no issues
- "warn"   : approved with minor issues noted (missing optional sections, style)
- "reject" : not approved -- missing critical content, unsurfaced breach, or hallucinated figures

Be strict on breaches and hallucinations; be lenient on style and formatting."""


class Validator:
    """Single-pass validator that produces a structured ValidationResult."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(ValidationResult)

    async def validate(
        self,
        task: str,
        agent_results: dict,
    ) -> ValidationResult:
        logger.info("validator_start", agents=list(agent_results.keys()))

        output_summary = _summarise_results(agent_results)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Original task: {task}\n\n"
                f"Agent outputs to review:\n\n{output_summary}\n\n"
                "Provide your validation decision."
            )),
        ]

        result: ValidationResult = await self.llm.ainvoke(messages)
        logger.info(
            "validator_done",
            approved=result.approved,
            severity=result.severity,
            issues=len(result.issues),
        )
        return result


def _summarise_results(agent_results: dict) -> str:
    """Format agent_results into a readable block for the LLM."""
    parts = []
    for agent_name, data in agent_results.items():
        status = data.get("status", "unknown") if isinstance(data, dict) else "unknown"
        if status == "stub":
            parts.append(f"[{agent_name}] -- not yet implemented (stub)")
            continue
        if status == "error":
            parts.append(f"[{agent_name}] -- ERROR: {data.get('error', 'unknown')}")
            continue
        result = data.get("result", data) if isinstance(data, dict) else data
        if hasattr(result, "model_dump"):
            result = json.dumps(result.model_dump(), indent=2)
        parts.append(f"[{agent_name}]\n{str(result)[:2000]}")
    return "\n\n".join(parts) if parts else "No agent outputs available."
