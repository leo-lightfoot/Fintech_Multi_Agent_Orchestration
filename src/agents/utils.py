"""Shared helpers used by multiple specialist agents."""
from typing import Optional


def extract_data_text(previous_results: Optional[dict]) -> str:
    """Return the DataAgent's text output from previous_results.

    All specialist agents (portfolio, risk) call this to get the
    raw data fetched by the DataAgent in the previous pipeline step.
    """
    if not previous_results:
        return "No data available."
    data_entry = previous_results.get("data", {})
    if isinstance(data_entry, dict):
        return str(data_entry.get("result", "No data available."))
    return str(data_entry)
