"""
Pricing State — State for the Pricing Analysis sub-graph agent.

Stores chat history, input context, and analysis results for pricing intelligence.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class PricingState(TypedDict):
    """State for the pricing analysis agent.

    Attributes:
        messages: Chat message history (agent + tool interactions).
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        analysis_result: Final pricing analysis output.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    analysis_result: str
