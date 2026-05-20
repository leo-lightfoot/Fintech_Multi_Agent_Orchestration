"""Ingest documents from data/docs/ into the ChromaDB vector store.

Run once before using document_search:
    python scripts/ingest_docs.py

Supported formats: .txt, .pdf
Chunks each document into ~500-character passages with 50-char overlap.
"""
import sys
import hashlib
from pathlib import Path

# Anchor all paths to the project root (scripts/ingest_docs.py -> root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.config import settings
from src.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_text(text: str, source: str) -> list[dict]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            uid = hashlib.md5(f"{source}:{start}".encode()).hexdigest()
            chunks.append({"id": uid, "text": chunk, "source": source, "start": start})
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.warning("pypdf_not_installed_skipping_pdf", file=str(path))
            return ""
    return ""


def main():
    import chromadb

    docs_path = (_PROJECT_ROOT / settings.docs_path).resolve()
    store_path = (_PROJECT_ROOT / settings.vector_store_path).resolve()
    store_path.mkdir(parents=True, exist_ok=True)

    if not docs_path.exists():
        print(f"Docs directory not found: {docs_path}")
        sys.exit(1)

    files = [f for f in docs_path.iterdir() if f.suffix.lower() in {".txt", ".pdf"}]
    if not files:
        print(f"No .txt or .pdf files found in {docs_path}")
        sys.exit(0)

    client = chromadb.PersistentClient(path=str(store_path))
    collection = client.get_or_create_collection("fund_documents")

    total_chunks = 0
    for fpath in sorted(files):
        text = read_file(fpath)
        if not text.strip():
            logger.warning("empty_or_unreadable", file=fpath.name)
            continue
        chunks = chunk_text(text, source=fpath.name)
        if not chunks:
            continue
        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{"source": c["source"], "start": c["start"]} for c in chunks],
        )
        total_chunks += len(chunks)
        print(f"  {fpath.name}: {len(chunks)} chunks")

    print(f"\nIngested {total_chunks} chunks from {len(files)} files into {store_path}")


if __name__ == "__main__":
    main()
