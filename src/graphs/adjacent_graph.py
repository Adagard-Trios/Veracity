"""
Adjacent Graph — Tool-calling agent graph for adjacent market analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.states.adjacent_state import AdjacentState
from src.nodes.adjacent_node import agent_node, adjacent_tools


# Build the graph
builder = StateGraph(AdjacentState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(adjacent_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
adjacent_graph = builder.compile()
