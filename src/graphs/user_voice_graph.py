"""
User Voice Graph — Context extraction + Parallel data collection + LLM compilation.

Architecture:
    __start__ → context_extractor → data_collector (parallel tools) → compiler → __end__

Focuses on positioning and messaging gaps (how to talk about what exists).
"""

from langgraph.graph import StateGraph, END
from src.states.user_voice_state import UserVoiceState
from src.nodes.user_voice_node import context_extractor, data_collector, compiler


# Build the graph
builder = StateGraph(UserVoiceState)

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
user_voice_graph = builder.compile()
