"""
Veracity Graph — Main orchestrator graph for the Growth Intelligence System.

Architecture:
    __start__ → information_fetcher → [6 parallel sub-graphs] → compiler_and_storage → __end__

The 6 parallel sub-graphs are:
    - adjacent_graph (adjacent market analysis)
    - competitor_graph (competitor analysis)
    - market_trend_graph (market trend analysis)
    - pricing_graph (pricing analysis)
    - user_voice_graph (user voice analysis)
    - win_loss_graph (win-loss analysis)
"""

import importlib
from langgraph.graph import StateGraph, END
from src.states.veracity_state import VeracityState
from src.nodes.veracity_node import information_fetcher, compiler_and_storage
from src.graphs.adjacent_graph import adjacent_graph
from src.graphs.competitor_graph import competitor_graph
from src.graphs.market_trend_graph import market_trend_graph
from src.graphs.pricing_graph import pricing_graph
from src.graphs.user_voice_graph import user_voice_graph

# Handle hyphenated module name for win-loss
_win_loss_graph_mod = importlib.import_module("src.graphs.win-loss_graph")
win_loss_graph = _win_loss_graph_mod.win_loss_graph


# ---------------------------------------------------------------------------
# Sub-graph wrapper nodes
# These wrap each compiled sub-graph so it can be invoked as a node in the
# main graph while passing/receiving the correct state slices.
# ---------------------------------------------------------------------------
def run_adjacent_analysis(state: VeracityState) -> dict:
    """Run the adjacent market analysis sub-graph."""
    result = adjacent_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"adjacent_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


def run_competitor_analysis(state: VeracityState) -> dict:
    """Run the competitor analysis sub-graph."""
    result = competitor_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"competitor_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


def run_market_trend_analysis(state: VeracityState) -> dict:
    """Run the market trend analysis sub-graph."""
    result = market_trend_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"market_trend_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


def run_pricing_analysis(state: VeracityState) -> dict:
    """Run the pricing analysis sub-graph."""
    result = pricing_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"pricing_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


def run_user_voice_analysis(state: VeracityState) -> dict:
    """Run the user voice analysis sub-graph."""
    result = user_voice_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"user_voice_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


def run_win_loss_analysis(state: VeracityState) -> dict:
    """Run the win-loss analysis sub-graph."""
    result = win_loss_graph.invoke({
        "messages": [],
        "category": state.get("category", ""),
        "fetched_content": state.get("fetched_content", []),
        "analysis_result": "",
    })
    return {"win_loss_analysis": {"analysis_result": result.get("analysis_result", ""), "messages": str(result.get("messages", []))}}


# ---------------------------------------------------------------------------
# Build the main Veracity graph
# ---------------------------------------------------------------------------
builder = StateGraph(VeracityState)

# Add nodes
builder.add_node("information_fetcher", information_fetcher)
builder.add_node("adjacent_analysis", run_adjacent_analysis)
builder.add_node("competitor_analysis", run_competitor_analysis)
builder.add_node("market_trend_analysis", run_market_trend_analysis)
builder.add_node("pricing_analysis", run_pricing_analysis)
builder.add_node("user_voice_analysis", run_user_voice_analysis)
builder.add_node("win_loss_analysis", run_win_loss_analysis)
builder.add_node("compiler_and_storage", compiler_and_storage)

# Edges: __start__ → information_fetcher
builder.set_entry_point("information_fetcher")

# Fan-out: information_fetcher → 6 parallel sub-graphs
builder.add_edge("information_fetcher", "adjacent_analysis")
builder.add_edge("information_fetcher", "competitor_analysis")
builder.add_edge("information_fetcher", "market_trend_analysis")
builder.add_edge("information_fetcher", "pricing_analysis")
builder.add_edge("information_fetcher", "user_voice_analysis")
builder.add_edge("information_fetcher", "win_loss_analysis")

# Fan-in: all 6 sub-graphs → compiler_and_storage
builder.add_edge("adjacent_analysis", "compiler_and_storage")
builder.add_edge("competitor_analysis", "compiler_and_storage")
builder.add_edge("market_trend_analysis", "compiler_and_storage")
builder.add_edge("pricing_analysis", "compiler_and_storage")
builder.add_edge("user_voice_analysis", "compiler_and_storage")
builder.add_edge("win_loss_analysis", "compiler_and_storage")

# compiler_and_storage → __end__
builder.add_edge("compiler_and_storage", END)

# Compile the graph
veracity_graph = builder.compile()
