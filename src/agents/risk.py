"""RiskAgent -- identifies limit breaches and exposure flags.

Receives raw data from DataAgent (limit_rules, positions tables) and
produces a structured RiskResult. Never suppresses a breach -- if
breached=1 in the data it must appear in the result.
"""
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.utils import extract_data_text
from src.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a risk and compliance analyst for a fintech solutions team.

You receive raw database data and produce a structured risk assessment covering:
- All limit breaches (breached=1 rows from limit_rules) -- MANDATORY, never omit
- Exposure summary by asset type and fund
- Overall risk status (ok / warning / breach)

Rules:
- A breached limit MUST appear in the breaches list -- never omit or soften one
- If breached=0 the rule is compliant -- still list it in flags as "ok"
- Severity: "critical" if current_value > 1.2 * limit_value, "warning" otherwise
- If no limit data is available, state that clearly in the summary
- Do not invent risk metrics not present in the data"""


class RiskFlag(BaseModel):
    rule_id: str
    fund_id: str
    rule_name: str
    rule_type: str
    limit_value: float
    current_value: float
    breached: bool
    severity: str = "ok"     # ok | warning | critical


class LimitBreach(BaseModel):
    rule_id: str
    fund_id: str
    rule_name: str
    limit_value: float
    current_value: float
    overshoot_pct: float     # (current - limit) / limit * 100


class RiskResult(BaseModel):
    overall_status: str = "ok"    # ok | warning | breach
    flags: list[RiskFlag] = Field(default_factory=list)
    breaches: list[LimitBreach] = Field(default_factory=list)
    summary: str = ""


class RiskAgent:
    """Produces structured risk assessment from data fetched by DataAgent."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(RiskResult)

    async def run(
        self,
        task: str,
        context: Optional[dict] = None,
        previous_results: Optional[dict] = None,
        validation_feedback: Optional[list[str]] = None,
    ) -> RiskResult:
        logger.info("risk_agent_start", task_preview=task[:80])

        data_text = extract_data_text(previous_results)

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

        result: RiskResult = await self.llm.ainvoke(messages)
        logger.info(
            "risk_agent_done",
            status=result.overall_status,
            breaches=len(result.breaches),
            flags=len(result.flags),
        )
        return result


