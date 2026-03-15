"""
Adjacent Graph \u2014 3-Stage Pipeline for Adjacent Market Analysis.

Architecture:
    context_extractor -> data_collector -> compiler -> END
"""

from langgraph.graph import StateGraph, END
from src.states.adjacent_state import AdjacentState
from src.nodes.adjacent_node import context_extractor, data_collector, compiler

# Build the graph
builder = StateGraph(AdjacentState)

# Add nodes
builder.add_node("context_extractor", context_extractor)
builder.add_node("data_collector", data_collector)
builder.add_node("compiler", compiler)

# Add edges
builder.set_entry_point("context_extractor")
builder.add_edge("context_extractor", "data_collector")
builder.add_edge("data_collector", "compiler")
builder.add_edge("compiler", END)

# Compile
adjacent_graph = builder.compile()
