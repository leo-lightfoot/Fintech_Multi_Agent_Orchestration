"""Responder agent -- formats agent results into a final markdown response."""
from typing import Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a response formatting assistant for a fintech solutions team.

Your job is to take raw outputs from specialist agents and produce a single, clear,
well-structured markdown response for the ops user.

Guidelines:
- Open with a one-sentence summary of what was done
- Present data in markdown tables where appropriate
- Flag any warnings, errors, or missing data clearly
- Keep language plain and professional -- no jargon
- Do not invent data; if an agent returned no result, say so explicitly
- End with a short "Next steps" section only if there are clear follow-up actions"""


class Responder:
    """Formats the combined outputs of all specialist agents into a user-facing response."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    async def format_response(
        self,
        task: str,
        results: dict[str, Any],
        summary: Optional[str] = None,
    ) -> str:
        """Format agent results into a final markdown response.

        Args:
            task: The original user task.
            results: Dict of agent_name -> {status, result} from the execute node.
            summary: Optional pre-built summary (unused for now, reserved for future).

        Returns:
            Formatted markdown string ready for the end user.
        """
        logger.info("formatting_response", task_preview=task[:80])

        agent_outputs = []
        for agent_name, data in results.items():
            status = data.get("status", "unknown")
            if status == "success":
                agent_outputs.append(f"**{agent_name.title()} agent**: {data.get('result', 'no output')}")
            elif status == "stub":
                agent_outputs.append(f"**{agent_name.title()} agent**: not yet implemented")
            else:
                agent_outputs.append(f"**{agent_name.title()} agent** (error): {data.get('error', 'unknown error')}")

        agent_summary = "\n\n".join(agent_outputs) if agent_outputs else "No agent results available."

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"User request: {task}\n\n"
                f"Agent outputs:\n\n{agent_summary}\n\n"
                "Format this into a final response for the ops user."
            )),
        ]

        response = await self.llm.ainvoke(messages)
        formatted: str = response.content

        logger.info("response_formatted", length=len(formatted))
        return formatted
