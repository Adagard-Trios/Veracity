"""
Veracity State — Main orchestrator state for the Growth Intelligence System.

Stores all inputs, fetched content, parallel sub-graph results, and final compiled report.
"""

from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class VeracityState(TypedDict):
    """Main state for the Veracity orchestrator graph.

    Attributes:
        category: The business/product category to analyze (REQUIRED).
        urls: List of website URLs to scrape for information.
        pdf_paths: List of file paths to PDF documents.
        txt_paths: List of file paths to text files.
        fetched_content: All raw content fetched/read from the provided sources.
        messages: Chat message history for the orchestrator.
        adjacent_analysis: Results from the adjacent market analysis sub-graph.
        competitor_analysis: Results from the competitor analysis sub-graph.
        market_trend_analysis: Results from the market trend analysis sub-graph.
        pricing_analysis: Results from the pricing analysis sub-graph.
        user_voice_analysis: Results from the user voice analysis sub-graph.
        win_loss_analysis: Results from the win-loss analysis sub-graph.
        sse_queue: Optional queue for SSE event emission (thread-safe queue.Queue
                   or equivalent). Set to None if SSE is not used.
        compiled_report: Final aggregated report from all sub-graphs.
        storage_status: Status message from ChromaDB storage operation.
    """

    # --- Inputs ---
    brand: str
    category: str
    query: str
    competitors: list[str]
    urls: list[str]
    pdf_paths: list[str]
    txt_paths: list[str]

    # --- Fetched Data ---
    fetched_content: list[str]

    # --- Chat History ---
    messages: Annotated[list, add_messages]

    # --- Sub-graph Results ---
    adjacent_analysis: dict
    competitor_analysis: dict
    market_trend_analysis: dict
    pricing_analysis: dict
    user_voice_analysis: dict
    win_loss_analysis: dict

    # --- Final Output ---
    compiled_report: dict
    storage_status: str
    sse_queue: Any           # optional — pass a queue.Queue to enable SSE emission
