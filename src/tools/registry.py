"""Tool registry -- maps agent names to the tools they are allowed to use.

Adding a new tool:
  1. Import it here (use lazy imports for heavy deps like chromadb)
  2. Add it to the relevant agent lists below

Adding a new agent:
  1. Add an entry in AGENT_TOOLS with the agent name as key
"""
from src.tools.sql import sql_query
from src.tools.excel import excel_query


def _get_document_search():
    """Lazy import -- avoids loading ChromaDB and the ONNX model at startup."""
    from src.tools.documents import document_search
    return document_search


def get_tools(agent_name: str) -> list:
    """Return the tool list for a given agent.

    document_search is loaded lazily so ChromaDB does not initialise
    until the data agent actually runs for the first time.
    """
    if agent_name == "data":
        return [sql_query, excel_query, _get_document_search()]
    if agent_name in ("portfolio", "risk"):
        return [sql_query]
    return []   # report and unknown agents get no tools
