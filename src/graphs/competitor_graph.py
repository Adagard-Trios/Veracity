"""
Competitor Graph — Dynamic parallel fan-out pipeline for competitor analysis.

Architecture:
    __start__
        │
    planner           ← LLM identifies 3-5 competitors; stores list in state
        │
    route_to_fetchers ← conditional EDGE function reads state, emits list[Send]
        │
    ┌───┴───┐         ← LangGraph runs these branches in parallel
    │  ...  │
    fetch_competitor  ← one branch per competitor; all 3 Firecrawl tools run
    │  ...  │           concurrently inside each branch (ThreadPoolExecutor)
    └───┬───┘
        │  results merged via operator.add reducer
    compiler          ← aggregates all parallel results → CompetitivePayload
        │
    __end__

Key rule: nodes must return dicts. list[Send] is only valid as a return from
a conditional EDGE function. planner_node → dict, route_to_fetchers → list[Send].
"""

from langgraph.graph import StateGraph, END
from langgraph.types import Send
from src.states.competitor_state import CompetitorStateSchema
from src.nodes.competitor_node import (
    planner_node,
    route_to_fetchers,
    competitor_fetch_node,
    compiler_node,
)


def build_competitor_graph():
    graph = StateGraph(CompetitorStateSchema)

    # Nodes
    graph.add_node("planner", planner_node)
    graph.add_node("fetch_competitor", competitor_fetch_node)
    graph.add_node("compiler", compiler_node)

    # Entry point
    graph.set_entry_point("planner")

    # planner (node) → route_to_fetchers (edge fn) → parallel fetch branches
    graph.add_conditional_edges(
        "planner",
        route_to_fetchers,              # reads state["competitor_tasks"], returns list[Send]
        ["fetch_competitor", "compiler"],  # allowed target nodes
    )

    # Each fetch branch feeds compiler (fan-in via operator.add on competitor_results)
    graph.add_edge("fetch_competitor", "compiler")

    # compiler is the terminal node
    graph.add_edge("compiler", END)

    return graph.compile()


competitor_graph = build_competitor_graph()
