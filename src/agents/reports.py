"""ReportAgent -- formats structured agent outputs into a markdown report.

Runs last in the pipeline. Receives outputs from data, portfolio, and risk
agents via previous_results and composes a single professional markdown document.
Does not call any tools or use structured output -- the output IS the markdown.
"""
import json
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Maps report type keywords to a brief format instruction
REPORT_TEMPLATES = {
    "performance": "Focus on NAV trends, P&L attribution, and top/bottom performers.",
    "risk":        "Lead with breaches, then flags, then overall exposure summary.",
    "mandate":     "Cover investment objective, allocation vs benchmark, compliance status.",
}

SYSTEM_PROMPT = """You are a report writer for a fintech solutions team.

You receive structured outputs from specialist analysis agents and compose a single,
professional markdown report for the ops user.

Report structure (adapt to what data is available):
1. Executive summary (2-3 sentences)
2. Portfolio overview (NAV, allocation table)
3. Risk and compliance (limit status, any breaches highlighted)
4. Key findings (bullet list)
5. Next steps (only if there are clear actions)

Formatting rules:
- Use markdown headers (##, ###)
- Use markdown tables for numeric data
- Bold any limit breaches or warnings
- Do not include raw JSON or dict repr in the output
- If a section has no data, omit it rather than writing "N/A"
- Keep the tone professional and concise"""


class ReportAgent:
    """Composes a final markdown report from all previous agent outputs."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def run(
        self,
        task: str,
        context: Optional[dict] = None,
        previous_results: Optional[dict] = None,
        validation_feedback: Optional[list[str]] = None,
    ) -> str:
        logger.info("report_agent_start", task_preview=task[:80])

        sections = _build_context_sections(previous_results or {})
        report_type = _detect_report_type(task)
        template_hint = REPORT_TEMPLATES.get(report_type, "")

        user_content = (
            f"Task: {task}\n\n"
            f"{template_hint}\n\n"
            f"Available analysis:\n\n{sections}"
        )
        if validation_feedback:
            user_content += (
                "\n\nPrevious draft was rejected -- fix these issues:\n"
                + "\n".join(f"- {i}" for i in validation_feedback)
            )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        response = await self.llm.ainvoke(messages)
        report: str = response.content
        logger.info("report_agent_done", length=len(report))
        return report


def _build_context_sections(previous_results: dict) -> str:
    """Serialise each agent's output into a readable block."""
    parts = []
    order = ["data", "portfolio", "risk"]   # deterministic section order
    remaining = [k for k in previous_results if k not in order]

    for key in order + remaining:
        if key not in previous_results:
            continue
        entry = previous_results[key]
        if isinstance(entry, dict):
            value = entry.get("result", entry.get("error", str(entry)))
        else:
            value = entry
        # Pydantic models serialise cleanly via model_dump
        if hasattr(value, "model_dump"):
            value = json.dumps(value.model_dump(), indent=2)
        parts.append(f"### {key.title()} agent output\n\n{value}")

    return "\n\n".join(parts) if parts else "No agent outputs available."


def _detect_report_type(task: str) -> str:
    lower = task.lower()
    if any(w in lower for w in ("risk", "breach", "limit", "compliance", "exposure")):
        return "risk"
    if any(w in lower for w in ("performance", "p&l", "attribution", "return")):
        return "performance"
    if any(w in lower for w in ("mandate", "objective", "benchmark")):
        return "mandate"
    return "performance"
