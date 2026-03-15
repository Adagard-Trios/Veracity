"""
Veracity Node — Main orchestrator nodes for the Growth Intelligence System.

Contains:
- information_fetcher: Validates inputs, scrapes URLs, reads PDFs/TXTs, merges content.
- compiler_and_storage: Aggregates all 6 sub-graph results, stores in ChromaDB.
"""

from datetime import datetime
from langchain_core.messages import HumanMessage
from src.states.veracity_state import VeracityState
from src.utils.utils import scrape_urls, read_pdf_files, read_txt_files, store_to_chromadb
from src.utils.sse import emit_sse_artifact
from src.utils.persistence_utils import persist_graph_run


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
        raise ValueError(
            "Category is required. Please provide a business/product category."
        )

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
            HumanMessage(
                content=(
                    f"Information fetched successfully for category '{category}'. "
                    f"Sources: {len(urls)} URLs, {len(pdf_paths)} PDFs, {len(txt_paths)} TXT files. "
                    f"Total content pieces: {len(all_content)}."
                )
            )
        ],
    }


def compiler_and_storage(state: VeracityState) -> dict:
    """Compile all sub-graph results and store in ChromaDB.

    Aggregates the analysis results from all 6 parallel sub-graphs
    into a unified compiled report and persists to ChromaDB.
    """
    category = state.get("category", "Unknown")

    # --- Emit SSE for competitor structured output (spec Step 6) ---
    competitor_output = state.get("competitor_analysis", {})
    structured = competitor_output.get("structured_output", {})
    confidence = structured.get("overall_confidence", 0.5) if structured else 0.5
    if structured:
        emit_sse_artifact(
            domain="competitive_landscape",
            payload=structured,
            confidence=confidence,
            sse_queue=state.get("sse_queue"),
        )

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

    # --- Store in ChromaDB via persist_graph_run ---
    storage_status = "No analyses to store."
    if any(compiled_report["analyses"].values()):
        try:
            persist_graph_run(
                graph_name="veracity_graph",
                state=dict(state),
                category=category,
                extra_metadata={
                    "compiled_timestamp": compiled_report["timestamp"],
                    "analyses_count": len(
                        [v for v in compiled_report["analyses"].values() if v]
                    ),
                },
            )
            stored_count = len([v for v in compiled_report["analyses"].values() if v])
            storage_status = (
                f"Successfully stored {stored_count} analyses in ChromaDB "
                f"(collection: graph_runs, graph: veracity_graph)."
            )
        except Exception as exc:
            storage_status = f"ChromaDB storage failed (non-fatal): {exc}"

    return {
        "compiled_report": compiled_report,
        "storage_status": storage_status,
        "messages": [
            HumanMessage(
                content=(
                    f"Compilation complete for category '{category}'. "
                    f"Status: {storage_status}"
                )
            )
        ],
    }
