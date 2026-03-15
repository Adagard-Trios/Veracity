"""
Win-Loss Graph — Tool-calling agent graph for win-loss analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

import importlib
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

# Handle hyphenated module names
_win_loss_state_mod = importlib.import_module("src.states.win-loss_state")
WinLossState = _win_loss_state_mod.WinLossState

_win_loss_node_mod = importlib.import_module("src.nodes.win-loss_node")
agent_node = _win_loss_node_mod.agent_node
win_loss_tools = _win_loss_node_mod.win_loss_tools


# Build the graph
builder = StateGraph(WinLossState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(win_loss_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
win_loss_graph = builder.compile()
