"""
Pricing Graph — Context extraction + Parallel data collection + LLM compilation.

Architecture:
    __start__ → context_extractor → data_collector (all tools in parallel) → compiler → __end__
"""

from langgraph.graph import StateGraph, END
from src.states.pricing_state import PricingState
from src.nodes.pricing_node import context_extractor, data_collector, compiler


# Build the graph
builder = StateGraph(PricingState)

# Add nodes
builder.add_node("context_extractor", context_extractor)
builder.add_node("data_collector", data_collector)
builder.add_node("compiler", compiler)

# Add edges: __start__ → context_extractor → data_collector → compiler → __end__
builder.set_entry_point("context_extractor")
builder.add_edge("context_extractor", "data_collector")
builder.add_edge("data_collector", "compiler")
builder.add_edge("compiler", END)

# Compile
pricing_graph = builder.compile()
