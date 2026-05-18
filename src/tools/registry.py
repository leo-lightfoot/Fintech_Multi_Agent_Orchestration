"""Tool registry -- maps agent names to the tools they are allowed to use.

Adding a new tool:
  1. Import it here
  2. Add it to the relevant agent lists below

Adding a new agent:
  1. Add an entry in AGENT_TOOLS with the agent name as key
"""
from src.tools.sql import sql_query

# Agents that only need read access to the database get sql_query.
# Document and Excel tools will be added here in Phase 2 when built.
AGENT_TOOLS: dict[str, list] = {
    "data":      [sql_query],
    "portfolio": [sql_query],
    "risk":      [sql_query],
    "report":    [],          # report agent works on structured data, no direct DB access
}


def get_tools(agent_name: str) -> list:
    """Return the tool list for a given agent name.

    Returns an empty list for unknown agents so callers don't crash.
    """
    return AGENT_TOOLS.get(agent_name, [])
