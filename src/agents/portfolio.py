"""PortfolioAgent -- analyses positions, P&L, and attribution.

Receives raw data from DataAgent via previous_results and uses the LLM
to produce a structured PortfolioResult. Does not make direct DB calls --
DataAgent handles all data fetching.
"""
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a portfolio analysis specialist for a fintech solutions team.

You receive raw data fetched from the database and produce a structured analysis covering:
- Position-level breakdown (asset, weight, market value)
- Top holdings by weight
- Asset type allocation (Equity / Bond / Commodity)
- NAV trend (latest vs previous)
- Any positions that look unusual (e.g. very high concentration)

Rules:
- Work only from the data provided -- do not invent figures
- If data is missing for a section, state "data not available" for that field
- Weights and values must match the source data exactly
- Warnings should be specific (e.g. "Microsoft at 13.3% is approaching the 15% single-stock limit")"""


class PositionSummary(BaseModel):
    asset_name: str
    asset_type: str
    weight_pct: float
    market_value_usd: float


class PortfolioResult(BaseModel):
    fund_id: str = ""
    fund_name: str = ""
    total_nav_usd: float = 0.0
    nav_change_pct: float = 0.0       # latest vs previous NAV
    top_holdings: list[PositionSummary] = Field(default_factory=list)
    allocation_by_type: dict[str, float] = Field(default_factory=dict)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class PortfolioAgent:
    """Produces structured portfolio analysis from data fetched by DataAgent."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(PortfolioResult)

    async def run(
        self,
        task: str,
        context: Optional[dict] = None,
        previous_results: Optional[dict] = None,
        validation_feedback: Optional[list[str]] = None,
    ) -> PortfolioResult:
        logger.info("portfolio_agent_start", task_preview=task[:80])

        data_text = _extract_data(previous_results)

        user_content = f"Task: {task}\n\nDatabase data:\n{data_text}"
        if validation_feedback:
            user_content += (
                "\n\nPrevious attempt was rejected -- address these issues:\n"
                + "\n".join(f"- {i}" for i in validation_feedback)
            )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        result: PortfolioResult = await self.llm.ainvoke(messages)
        logger.info(
            "portfolio_agent_done",
            fund=result.fund_id,
            warnings=len(result.warnings),
        )
        return result


def _extract_data(previous_results: Optional[dict]) -> str:
    """Pull the data agent's text output from previous_results."""
    if not previous_results:
        return "No data available."
    data_entry = previous_results.get("data", {})
    if isinstance(data_entry, dict):
        return str(data_entry.get("result", "No data available."))
    return str(data_entry)
