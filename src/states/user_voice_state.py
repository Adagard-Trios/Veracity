"""
User Voice State — State for the User Voice Analysis sub-graph agent.

Stores chat history, input context, and analysis results for customer voice intelligence.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class UserVoiceState(TypedDict):
    """State for the user voice analysis agent.

    Attributes:
        messages: Chat message history (agent + tool interactions).
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        analysis_result: Final user voice analysis output.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    analysis_result: str
