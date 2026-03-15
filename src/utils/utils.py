"""
Utility tools for the Growth Intelligence Multi-Agent Decision System.

Provides functions for:
- Web scraping via Firecrawl
- PDF file reading via PyPDF2
- TXT file reading
- ChromaDB storage and querying
"""

import os
import uuid
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from PyPDF2 import PdfReader
import chromadb
from chromadb.config import Settings

load_dotenv()

# ---------------------------------------------------------------------------
# ChromaDB client (persistent local storage)
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "chroma_db")

_chroma_client = chromadb.Client(Settings(
    persist_directory=CHROMA_PERSIST_DIR,
    is_persistent=True,
    anonymized_telemetry=False,
))


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
            scraped = app.scrape_url(url, params={"formats": ["markdown"]})
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
            results.append(f"[Source: {path}]\n{full_text}" if full_text else f"[Source: {path}]\n(No text extracted)")
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
            results.append(f"[Source: {path}]\n{content}" if content else f"[Source: {path}]\n(Empty file)")
        except Exception as e:
            results.append(f"[Source: {path}]\n(Error reading file: {e})")

    return results


# ---------------------------------------------------------------------------
# ChromaDB — Storage
# ---------------------------------------------------------------------------
def store_to_chromadb(
    collection_name: str,
    documents: list[str],
    metadatas: list[dict] | None = None,
    ids: list[str] | None = None,
) -> str:
    """Store documents into a ChromaDB collection.

    Args:
        collection_name: Name of the ChromaDB collection.
        documents: List of document strings to store.
        metadatas: Optional list of metadata dicts (one per document).
        ids: Optional list of unique IDs (auto-generated if not provided).

    Returns:
        Confirmation message with the number of documents stored.
    """
    if not documents:
        return "No documents to store."

    collection = _chroma_client.get_or_create_collection(name=collection_name)

    if ids is None:
        ids = [str(uuid.uuid4()) for _ in documents]
    if metadatas is None:
        metadatas = [{"index": i} for i in range(len(documents))]

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    return f"Successfully stored {len(documents)} documents in collection '{collection_name}'."


def query_chromadb(
    collection_name: str,
    query: str,
    n_results: int = 5,
) -> list[str]:
    """Query a ChromaDB collection for relevant documents.

    Args:
        collection_name: Name of the ChromaDB collection to query.
        query: The query string.
        n_results: Number of results to return.

    Returns:
        List of matching document strings.
    """
    try:
        collection = _chroma_client.get_collection(name=collection_name)
        results = collection.query(query_texts=[query], n_results=n_results)
        return results.get("documents", [[]])[0]
    except Exception as e:
        return [f"(Error querying ChromaDB: {e})"]
