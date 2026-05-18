"""DataAgent — fetches data from the fintech database using tool calls.

The agent runs a standard tool-calling loop:
  1. Send task to LLM (with sql_query tool bound)
  2. LLM returns tool calls → execute them → append results
  3. Repeat until LLM responds with no tool calls (or MAX_ITERATIONS reached)
  4. Return the final structured response

All other specialist agents (portfolio, risk, report) receive this agent's
output as their starting context via previous_results.
"""
from typing import Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage

from src.tools.registry import get_tools
from src.utils.logging import get_logger

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = """You are a data retrieval agent for a fintech solutions team.

Your job is to fetch relevant data from the database to answer the user's request.
Use the sql_query tool to run SELECT queries. You may call it multiple times
if you need data from different tables.

Database tables available:
  - funds(fund_id, fund_name, fund_type, aum_usd, currency, manager)
  - positions(position_id, fund_id, asset_name, asset_type, quantity,
              price_usd, market_value_usd, weight_pct, as_of_date)
  - trades(trade_id, fund_id, asset_name, trade_type, quantity,
           price_usd, trade_date, status)
  - nav_history(nav_id, fund_id, nav_per_unit, total_nav_usd, as_of_date)
  - limit_rules(rule_id, fund_id, rule_name, rule_type,
                limit_value, current_value, breached, as_of_date)

Fund IDs: F001 (Alpha Growth), F002 (Beta Income), F003 (Gamma Balanced).

Rules:
- Only fetch what is needed for the request — do not over-query
- If a query returns no rows say so clearly — do not invent data
- Summarise the retrieved data in plain text after fetching it
- breached=1 in limit_rules means the limit has been violated"""


class DataAgent:
    """Fetches and summarises fintech data via SQL tool calls."""

    def __init__(self, llm: BaseChatModel):
        self.tools = get_tools("data")
        self.llm = llm.bind_tools(self.tools)
        # Plain LLM (no tools) for the final summary step
        self.llm_plain = llm

    async def run(
        self,
        task: str,
        context: Optional[dict] = None,
        previous_results: Optional[dict] = None,
        validation_feedback: Optional[list[str]] = None,
    ) -> str:
        """Fetch data relevant to the task and return a structured summary.

        Args:
            task: The user's original request.
            context: Optional extra context from the API request.
            previous_results: Results from agents that ran before this one (unused by data agent).
            validation_feedback: Issues from the validator on a retry pass.

        Returns:
            Plain-text summary of the data retrieved.
        """
        logger.info("data_agent_start", task_preview=task[:80])

        user_content = task
        if validation_feedback:
            user_content += (
                "\n\nNote — previous attempt was rejected. Please address these issues:\n"
                + "\n".join(f"- {i}" for i in validation_feedback)
            )
        if context:
            user_content += f"\n\nAdditional context: {context}"

        messages: list = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        # Tool-calling loop
        for iteration in range(MAX_TOOL_ITERATIONS):
            response: AIMessage = await self.llm.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                # LLM is done — return its final text
                logger.info("data_agent_done", iterations=iteration + 1)
                return response.content

            # Execute every tool call the LLM requested
            for call in response.tool_calls:
                result = await self._run_tool(call)
                messages.append(
                    ToolMessage(content=result, tool_call_id=call["id"])
                )

        # Fallback if we hit the iteration cap — ask for a plain summary
        logger.warning("data_agent_max_iterations_reached")
        messages.append(HumanMessage(content="Summarise the data you have retrieved so far."))
        final = await self.llm_plain.ainvoke(messages)
        return final.content

    async def _run_tool(self, tool_call: dict) -> str:
        """Dispatch a single tool call and return its string result."""
        name = tool_call["name"]
        args = tool_call.get("args", {})

        tool_map = {t.name: t for t in self.tools}
        if name not in tool_map:
            return f"Error: unknown tool '{name}'"

        try:
            result = await tool_map[name].ainvoke(args)
            logger.debug("tool_executed", tool=name, result_preview=str(result)[:120])
            return str(result)
        except Exception as exc:
            logger.error("tool_execution_failed", tool=name, error=str(exc))
            return f"Error running {name}: {exc}"
