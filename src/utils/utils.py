"""
Utility tools for the Growth Intelligence Multi-Agent Decision System.

Provides functions for:
- Web scraping via Firecrawl
- PDF file reading via PyPDF2
- TXT file reading
- ChromaDB storage and querying (deprecated shims — use persistence_utils instead)
"""

import os
import uuid
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from PyPDF2 import PdfReader
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

# ---------------------------------------------------------------------------
# ChromaDB Client (LangChain + HuggingFace Embeddings)
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "chroma_db")

# Automatically downloads and uses the all-MiniLM-L6-v2 model locally
hf_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
# ChromaDB — DEPRECATED shims
#
# The old chromadb.Client(Settings(...)) API is no longer used.
# All new code should import from src.utils.persistence_utils directly.
# These two functions are kept only for backwards-compatibility with any
# external callers that may still reference them.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Firecrawl — Web Scraping
# ---------------------------------------------------------------------------
def scrape_urls(urls: list[str]) -> list[str]:
    """Scrape website content from a list of URLs using Firecrawl.

    Args:
        urls: List of website URLs to scrape.

    Returns:
        List of scraped text content strings (one per URL).
    """
    if not urls:
        return []

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY not found in environment variables.")

    app = FirecrawlApp(api_key=api_key)
    results = []

    for url in urls:
        try:
            scraped = app.scrape(url, formats=["markdown"])
            content = scraped.get("markdown", "") if isinstance(scraped, dict) else str(scraped)
            if content:
                results.append(f"[Source: {url}]\n{content}")
            else:
                results.append(f"[Source: {url}]\n(No content extracted)")
        except Exception as e:
            results.append(f"[Source: {url}]\n(Error scraping: {e})")

    return results


# ---------------------------------------------------------------------------
# PDF Reader
# ---------------------------------------------------------------------------
def read_pdf_files(pdf_paths: list[str]) -> list[str]:
    """Read text content from PDF files.

    Args:
        pdf_paths: List of file paths to PDF documents.

    Returns:
        List of extracted text strings (one per PDF).
    """
    if not pdf_paths:
        return []

    results = []
    for path in pdf_paths:
        try:
            reader = PdfReader(path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            full_text = "\n".join(text_parts)
            results.append(
                f"[Source: {path}]\n{full_text}"
                if full_text
                else f"[Source: {path}]\n(No text extracted)"
            )
        except Exception as e:
            results.append(f"[Source: {path}]\n(Error reading PDF: {e})")

    return results


# ---------------------------------------------------------------------------
# TXT Reader
# ---------------------------------------------------------------------------
def read_txt_files(txt_paths: list[str]) -> list[str]:
    """Read content from plain text files.

    Args:
        txt_paths: List of file paths to text files.

    Returns:
        List of file content strings (one per file).
    """
    if not txt_paths:
        return []

    results = []
    for path in txt_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            results.append(
                f"[Source: {path}]\n{content}"
                if content
                else f"[Source: {path}]\n(Empty file)"
            )
        except Exception as e:
            results.append(f"[Source: {path}]\n(Error reading file: {e})")

    return results


# ---------------------------------------------------------------------------
# ChromaDB — Storage (via LangChain Chroma)
# ChromaDB — Deprecated shims
#
# These functions are kept for backwards-compatibility only.
# All new code should use src.utils.persistence_utils directly.
# ---------------------------------------------------------------------------
def store_to_chromadb(
    collection_name: str,
    documents: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> str:
    """DEPRECATED — delegate to persistence_utils.persist_graph_run instead.

    Kept for backwards-compatibility. New code should call
    ``persist_graph_run`` from ``src.utils.persistence_utils``.
    """
    import warnings

    warnings.warn(
        "store_to_chromadb is deprecated. Use persist_graph_run from "
        "src.utils.persistence_utils instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from src.utils.persistence_utils import _get_collection
    import uuid as _uuid

    if not documents:
        return "No documents to store."

    col = _get_collection(collection_name)
    if ids is None:
        ids = [str(_uuid.uuid4()) for _ in documents]
    safe_metas: list[dict] = []
    for i, m in enumerate(metadatas or []):
        safe_metas.append(
            {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool))}
            if m
            else {"index": i}
        )
    if not safe_metas:
        safe_metas = [{"index": i} for i in range(len(documents))]

    col.upsert(documents=documents, metadatas=safe_metas, ids=ids)  # type: ignore[arg-type]
    return f"Successfully stored {len(documents)} documents in collection '{collection_name}'."


def query_chromadb(
    collection_name: str,
    query: str,
    n_results: int = 5,
) -> list[str]:
    """DEPRECATED — delegate to persistence_utils.retrieve_past_runs instead.

    Kept for backwards-compatibility. New code should call
    ``retrieve_past_runs`` from ``src.utils.persistence_utils``.
    """
    import warnings

    warnings.warn(
        "query_chromadb is deprecated. Use retrieve_past_runs from "
        "src.utils.persistence_utils instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from src.utils.persistence_utils import _get_client

    try:
        col = _get_client().get_collection(name=collection_name)
        results = col.query(query_texts=[query], n_results=n_results)
        docs = (results.get("documents") or [[]])[0]
        return docs  # type: ignore[return-value]
    except Exception as e:
        return [f"(Error querying ChromaDB: {e})"]
