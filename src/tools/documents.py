"""Document tool -- semantic search over the fund document store (ChromaDB).

Documents are ingested from data/docs/ by running scripts/ingest_docs.py.
The collection is persisted to data/chroma/ and reloaded on startup.

If the collection is empty (not yet ingested), searches return a helpful
message rather than crashing.
"""
from pathlib import Path
from langchain_core.tools import tool

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "fund_documents"
# Anchor to project root (src/tools/documents.py -> root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_client = None
_collection = None


def _get_collection():
    """Lazily initialise the ChromaDB collection."""
    global _client, _collection
    if _collection is not None:
        return _collection

    import chromadb
    # Resolve relative to project root, not CWD
    persist_path = str((_PROJECT_ROOT / settings.vector_store_path).resolve())
    _client = chromadb.PersistentClient(path=persist_path)

    try:
        _collection = _client.get_collection(COLLECTION_NAME)
        logger.info("chroma_collection_loaded", name=COLLECTION_NAME)
    except Exception:
        # Collection doesn't exist yet -- create empty one
        _collection = _client.get_or_create_collection(COLLECTION_NAME)
        logger.warning("chroma_collection_empty_run_ingest")

    return _collection


@tool
def document_search(query: str, n_results: int = 5) -> str:
    """Search fund documents (mandates, policies, prospectuses) for relevant passages.

    Args:
        query: Natural language search query.
        n_results: Number of passages to return (default 5).

    Returns:
        Relevant text passages with their source document names.
    """
    return _search(query, n_results)


def _search(query: str, n_results: int = 5) -> str:
    """Core search -- callable directly in tests."""
    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            return (
                "Document store is empty. "
                "Run 'python scripts/ingest_docs.py' to ingest documents from data/docs/."
            )

        results = collection.query(query_texts=[query], n_results=min(n_results, count))
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return f"No relevant documents found for: {query}"

        parts = []
        for doc, meta in zip(documents, metadatas):
            source = meta.get("source", "unknown") if meta else "unknown"
            parts.append(f"[{source}]\n{doc}")

        logger.info("document_search_ok", query_preview=query[:60], hits=len(parts))
        return "\n\n---\n\n".join(parts)

    except Exception as exc:
        logger.error("document_search_failed", error=str(exc))
        return f"Search failed: {exc}"
