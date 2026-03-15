"""
Market Trend State — State for the Market Trend Analysis sub-graph agent.

Stores chat history, input context, and analysis results for market trend intelligence.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class MarketTrendState(TypedDict):
    """State for the market trend analysis agent.

    Attributes:
        messages: Chat message history (agent + tool interactions).
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        analysis_result: Final market trend analysis output.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    analysis_result: str
