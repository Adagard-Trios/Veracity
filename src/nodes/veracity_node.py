"""
Veracity Node — Main orchestrator nodes for the Growth Intelligence System.

Contains:
- information_fetcher: Validates inputs, scrapes URLs, reads PDFs/TXTs, merges content.
- compiler_and_storage: Aggregates all 6 sub-graph results, stores in ChromaDB.
"""

import json
from datetime import datetime
from langchain_core.messages import HumanMessage
from src.states.veracity_state import VeracityState
from src.utils.utils import scrape_urls, read_pdf_files, read_txt_files, store_to_chromadb


def information_fetcher(state: VeracityState) -> dict:
    """Fetch information from all provided sources.

    Validates that:
    - category is provided (required)
    - at least one of urls, pdf_paths, or txt_paths is provided

    Then scrapes/reads all sources and merges into fetched_content.
    """
    category = state.get("category", "")
    urls = state.get("urls", [])
    pdf_paths = state.get("pdf_paths", [])
    txt_paths = state.get("txt_paths", [])

    # --- Validation ---
    if not category or not category.strip():
        raise ValueError("Category is required. Please provide a business/product category.")

    has_urls = bool(urls)
    has_pdfs = bool(pdf_paths)
    has_txts = bool(txt_paths)

    if not (has_urls or has_pdfs or has_txts):
        raise ValueError(
            "At least one data source is required. "
            "Please provide URLs, PDF file paths, or TXT file paths."
        )

    # --- Fetch from all sources ---
    all_content = []

    if has_urls:
        url_content = scrape_urls(urls)
        all_content.extend(url_content)

    if has_pdfs:
        pdf_content = read_pdf_files(pdf_paths)
        all_content.extend(pdf_content)

    if has_txts:
        txt_content = read_txt_files(txt_paths)
        all_content.extend(txt_content)

    return {
        "fetched_content": all_content,
        "messages": [
            HumanMessage(content=(
                f"Information fetched successfully for category '{category}'. "
                f"Sources: {len(urls)} URLs, {len(pdf_paths)} PDFs, {len(txt_paths)} TXT files. "
                f"Total content pieces: {len(all_content)}."
            ))
        ],
    }


def compiler_and_storage(state: VeracityState) -> dict:
    """Compile all sub-graph results and store in ChromaDB.

    Aggregates the analysis results from all 6 parallel sub-graphs
    into a unified compiled report and persists to ChromaDB.
    """
    category = state.get("category", "Unknown")

    # --- Aggregate results ---
    compiled_report = {
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "analyses": {
            "adjacent_market": state.get("adjacent_analysis", {}),
            "competitor": state.get("competitor_analysis", {}),
            "market_trend": state.get("market_trend_analysis", {}),
            "pricing": state.get("pricing_analysis", {}),
            "user_voice": state.get("user_voice_analysis", {}),
            "win_loss": state.get("win_loss_analysis", {}),
        },
    }

    # --- Prepare documents for ChromaDB ---
    documents = []
    metadatas = []

    for analysis_name, analysis_data in compiled_report["analyses"].items():
        if analysis_data:
            doc_content = json.dumps(analysis_data) if isinstance(analysis_data, dict) else str(analysis_data)
            documents.append(doc_content)
            metadatas.append({
                "category": category,
                "analysis_type": analysis_name,
                "timestamp": compiled_report["timestamp"],
            })

    # --- Store in ChromaDB ---
    storage_status = "No documents to store."
    if documents:
        collection_name = f"veracity_{category.lower().replace(' ', '_')}"
        storage_status = store_to_chromadb(
            collection_name=collection_name,
            documents=documents,
            metadatas=metadatas,
        )

    return {
        "compiled_report": compiled_report,
        "storage_status": storage_status,
        "messages": [
            HumanMessage(content=(
                f"Compilation complete. {len(documents)} analyses stored in ChromaDB. "
                f"Status: {storage_status}"
            ))
        ],
    }
