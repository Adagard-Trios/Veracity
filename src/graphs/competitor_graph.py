"""
Competitor Graph — Tool-calling agent graph for competitor analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.states.competitor_state import CompetitorState
from src.nodes.competitor_node import agent_node, competitor_tools


# Build the graph
builder = StateGraph(CompetitorState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(competitor_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
competitor_graph = builder.compile()
