"""
Market Trend Graph — Tool-calling agent graph for market trend analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.states.market_trend_state import MarketTrendState
from src.nodes.market_trend_node import agent_node, market_trend_tools


# Build the graph
builder = StateGraph(MarketTrendState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(market_trend_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
market_trend_graph = builder.compile()
