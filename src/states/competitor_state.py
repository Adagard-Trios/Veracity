"""
Competitor State — State for the Competitor Analysis sub-graph agent.

Stores chat history, input context, per-competitor fetch results (merged from
parallel branches), and the final compiled analysis.
"""

import operator
from typing import Annotated, Any
from langgraph.graph.message import add_messages


class CompetitorState(dict):
    """State for the competitor analysis agent.

    Key fields:
        messages:           Chat message history (Annotated with add_messages reducer).
        category:           The business/product category being analyzed.
        fetched_content:    Raw pre-fetched content passed in from information_fetcher.
        competitor_results: List of per-competitor dicts from parallel fetch nodes.
                            Uses operator.add reducer — parallel writes are merged.
        analysis_result:    Plain-text summary (backward compat with main compiler).
        structured_output:  CompetitivePayload as dict for SSE emit.
    """
    pass


# LangGraph state schema as TypedDict annotations applied at graph build time.
# We use a plain dict subclass above so runtime state access is flexible, and
# declare the schema separately for the StateGraph constructor.

from typing import TypedDict


class CompetitorStateSchema(TypedDict):
    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    competitor_tasks: list                              # planner output — list of CompetitorTask dicts
    competitor_results: Annotated[list, operator.add]   # parallel-merge reducer
    analysis_result: str                                # kept — main compiler reads this
    structured_output: dict[str, Any]                   # new — CompetitivePayload as dict
