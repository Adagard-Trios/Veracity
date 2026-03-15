"""
Adjacent State — State for the Adjacent Market Analysis sub-graph agent.

Stores chat history, input context, and analysis results for adjacent market intelligence.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AdjacentState(TypedDict):
    """State for the adjacent market analysis agent.

    Attributes:
        messages: Chat message history (agent + tool interactions).
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        analysis_result: Final adjacent market analysis output.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    analysis_result: str
