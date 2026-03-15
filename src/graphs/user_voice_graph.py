"""
User Voice Graph — Tool-calling agent graph for user voice analysis.

Architecture: __start__ → agent → (tool calls loop) → __end__
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from src.states.user_voice_state import UserVoiceState
from src.nodes.user_voice_node import agent_node, user_voice_tools


# Build the graph
builder = StateGraph(UserVoiceState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(user_voice_tools))

# Add edges
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

# Compile
user_voice_graph = builder.compile()
