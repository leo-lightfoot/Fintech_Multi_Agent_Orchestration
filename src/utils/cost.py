"""LLM cost tracking via LangChain callbacks.

Usage:
    from src.utils.cost import CostCallback
    from langchain_core.runnables import RunnableConfig

    # Pass to any LangGraph/LangChain ainvoke call:
    config = RunnableConfig(callbacks=[CostCallback(state["cost_tracking"])])
    result = await graph.ainvoke(state, config)

The callback fires on every LLM call within the graph and accumulates
real token counts into the CostTracking object in state.
"""
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# USD per 1 million tokens (input / output)
# Update when model pricing changes.
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":     {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":       {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5":      {"input": 0.80,  "output": 4.00},
    "gpt-4o":                {"input": 2.50,  "output": 10.00},
    "gpt-4-turbo":           {"input": 10.00, "output": 30.00},
    "gpt-4o-mini":           {"input": 0.15,  "output": 0.60},
    # Fallback used when the model name is not found in the table
    "_default":              {"input": 3.00,  "output": 15.00},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost for a single LLM call."""
    pricing = PRICING.get(model) or PRICING["_default"]
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


class CostCallback(BaseCallbackHandler):
    """Accumulates real token counts and USD cost into a CostTracking object.

    Attach via RunnableConfig so it fires for every LLM call in the graph:

        config = RunnableConfig(callbacks=[CostCallback(state["cost_tracking"])])
        await graph.ainvoke(state, config)
    """

    def __init__(self, tracking, model: str | None = None):
        super().__init__()
        self.tracking = tracking
        self.model = model or settings.llm_model

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        try:
            usage = {}
            if response.llm_output:
                # Anthropic returns usage under "usage" key
                # OpenAI returns it under "token_usage"
                usage = (
                    response.llm_output.get("usage")
                    or response.llm_output.get("token_usage")
                    or {}
                )

            input_tokens = int(
                usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            )
            output_tokens = int(
                usage.get("output_tokens") or usage.get("completion_tokens") or 0
            )

            if input_tokens == 0 and output_tokens == 0:
                return  # no data -- skip rather than recording zeros

            cost = calculate_cost(self.model, input_tokens, output_tokens)

            self.tracking.llm_calls += 1
            self.tracking.tokens_used += input_tokens + output_tokens
            self.tracking.total_cost_usd += cost

            logger.debug(
                "llm_cost_recorded",
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=round(cost, 6),
            )

        except Exception as exc:
            # Cost tracking must never crash the main flow
            logger.warning("cost_callback_error", error=str(exc))
