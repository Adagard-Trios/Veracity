"""
Win/Loss Graph — LangGraph graph for the Win/Loss Intelligence Agent.

Architecture
────────────

  START
    │
    ▼
  wl_orchestrator_node                 ← LLM selects which buyer-signal sources to query
    │
    │  [conditional_edges → dispatch_to_signal_sources]
    │  Returns [Send("wl_fetch_node", {...})] — one per chosen source.
    │  LangGraph executes all Sends concurrently (true parallelism).
    │
    ▼  ── ── ── ── ── ── ── ── ── ── ── ── ── PARALLEL FAN-OUT ── ── ──
  wl_fetch_node(reddit)
  wl_fetch_node(hn)                    ← DYNAMIC: count varies per query
  wl_fetch_node(google_news)
  wl_fetch_node(g2_reviews)           ← Each returns {"raw_signals": [...]}
  wl_fetch_node(capterra_reviews)     ← operator.add merges all results
  wl_fetch_node(trustpilot)                into WinLossState.raw_signals
    │  ── ── ── ── ── ── ── ── ── ── ── ── ── ── FAN-IN ── ── ── ── ──
    │
    ▼
  wl_signal_extractor_node             ← Partitions raw_signals into per-source tasks
    │                                    Builds extraction_tasks list
    │
    │  [conditional_edges → dispatch_to_extractors]
    │  Returns [Send("wl_extract_node", {...})] — one per source with data.
    │  LangGraph executes all Sends concurrently (true parallelism).
    │
    ▼  ── ── ── ── ── ── ── ── ── ── ── ── ── PARALLEL FAN-OUT ── ── ──
  wl_extract_node(reddit)
  wl_extract_node(g2_reviews)         ← DYNAMIC: one per source that had data
  wl_extract_node(capterra_reviews)
    │  ── ── ── ── ── ── ── ── ── ── ── ── ── ── FAN-IN ── ── ── ── ──
    │  Each returns {"extracted_signals": ["[SOURCE]\\n..."]}
    │  operator.add merges all into WinLossState.extracted_signals
    │
    ▼
  wl_synthesizer_node                  ← Builds Win/Loss Signal Matrix +
    │                                    confidence scores + executive report
    ▼
  END

Key LangGraph patterns used
───────────────────────────
1. Send API (langgraph.types.Send) — used TWICE for dynamic parallel fan-out.
   Phase 1: dispatch_to_signal_sources() → [Send("wl_fetch_node", {...})] × N
   Phase 2: dispatch_to_extractors() → [Send("wl_extract_node", {...})] × M
   LangGraph executes all Sends in each phase concurrently in the same superstep.

2. Annotated[list[T], operator.add] reducers
   Phase 1: raw_signals — all wl_fetch_node calls append without conflict.
   Phase 2: extracted_signals — all wl_extract_node calls append without conflict.

3. add_conditional_edges with target node name(s) in a list
   Required to make the Send API work: the graph must know the target node
   is a valid destination for conditional routing.

Usage example
─────────────
  from src.graphs.win_loss_graph import win_loss_graph

  result = win_loss_graph.invoke({
      "messages": [],
      "brand": "Notion",
      "category": "B2B SaaS productivity / knowledge management",
      "competitors": ["Confluence", "Coda", "Obsidian"],
      "query": "Why do customers choose Notion over Confluence, and where do we lose enterprise deals?",
      "sources": [],
      "raw_signals": [],
      "extraction_tasks": [],
      "extracted_signals": [],
      "signal_matrix": "",
      "win_loss_report": "",
  })

  print(result["win_loss_report"])
  print(result["signal_matrix"])
"""

from langgraph.graph import StateGraph, START, END

from src.states.win_loss_state import WinLossState
from src.nodes.win_loss_node import (
    dispatch_to_extractors,
    dispatch_to_signal_sources,
    wl_fetch_node,
    wl_orchestrator_node,
    wl_extract_node,
    wl_signal_extractor_node,
    wl_synthesizer_node,
)

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
builder = StateGraph(WinLossState)

# ── Nodes ──────────────────────────────────────────────────────────────────

# Phase 1: orchestrator decides sources, fetch node collects signals in parallel
builder.add_node("wl_orchestrator_node", wl_orchestrator_node)
builder.add_node("wl_fetch_node", wl_fetch_node)

# Phase 2: extractor partitions signals, extract nodes run in parallel, synthesizer fans in
builder.add_node("wl_signal_extractor_node", wl_signal_extractor_node)
builder.add_node("wl_extract_node", wl_extract_node)
builder.add_node("wl_synthesizer_node", wl_synthesizer_node)

# ── Edges ──────────────────────────────────────────────────────────────────

# Entry: START → orchestrator
builder.add_edge(START, "wl_orchestrator_node")

# Phase 1 dynamic parallel fan-out:
# orchestrator → [Send("wl_fetch_node", {...}) × N sources]
builder.add_conditional_edges(
    "wl_orchestrator_node",
    dispatch_to_signal_sources,
    ["wl_fetch_node"],
)

# Phase 1 fan-in: all wl_fetch_node completions → wl_signal_extractor_node
# LangGraph waits for ALL parallel Sends to complete before moving forward.
builder.add_edge("wl_fetch_node", "wl_signal_extractor_node")

# Phase 2 dynamic parallel fan-out:
# extractor → [Send("wl_extract_node", {...}) × M tasks]
builder.add_conditional_edges(
    "wl_signal_extractor_node",
    dispatch_to_extractors,
    ["wl_extract_node"],
)

# Phase 2 fan-in: all wl_extract_node completions → wl_synthesizer_node
# LangGraph waits for ALL parallel extraction Sends to complete before synthesising.
builder.add_edge("wl_extract_node", "wl_synthesizer_node")

# Final edge: synthesizer → END
builder.add_edge("wl_synthesizer_node", END)

# ── Compile ────────────────────────────────────────────────────────────────
win_loss_graph = builder.compile()
