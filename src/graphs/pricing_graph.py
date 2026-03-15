"""
Pricing Graph — Tool-calling agent graph for pricing analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.states.pricing_state import PricingState
from src.nodes.pricing_node import agent_node, pricing_tools


# Build the graph
builder = StateGraph(PricingState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(pricing_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
pricing_graph = builder.compile()
