"""
Marketing Trend Graph — LangGraph graph for the Marketing & Trend Agent.

Architecture
────────────

  START
    │
    ▼
  orchestrator_node                    ← LLM selects which sources to query
    │
    │  [conditional_edges → dispatch_to_sources]
    │  Returns [Send("fetch_source_node", {...})] — one per chosen source.
    │  LangGraph executes all Sends concurrently (true parallelism).
    │
    ▼  ── ── ── ── ── ── ── ── ── ── ── ── ── PARALLEL FAN-OUT ── ── ──
  fetch_source_node(meta_ads)
  fetch_source_node(google_trends)     ← DYNAMIC: count varies per query
  fetch_source_node(google_news)
  fetch_source_node(reddit)            ← Each returns {"raw_data": [...]}
  fetch_source_node(hn)                ← operator.add merges all results
  fetch_source_node(patents)                into MarketingTrendState.raw_data
    │  ── ── ── ── ── ── ── ── ── ── ── ── ── ── FAN-IN ── ── ── ── ──
    │
    ▼
  analysis_dispatcher_node             ← Partitions raw_data into tool slices
    │                                    Builds analysis_tasks list
    │
    │  [conditional_edges → dispatch_to_analysis_tools]
    │  Returns [Send("run_analysis_tool_node", {...})] — one per tool.
    │  LangGraph executes all Sends concurrently (true parallelism).
    │
    ▼  ── ── ── ── ── ── ── ── ── ── ── ── ── PARALLEL FAN-OUT ── ── ──
  run_analysis_tool_node(ad_analysis)
  run_analysis_tool_node(trend_analysis)   ← DYNAMIC: 2–3 tools depending
  run_analysis_tool_node(patent_analysis)    on whether patents were fetched
    │  ── ── ── ── ── ── ── ── ── ── ── ── ── ── FAN-IN ── ── ── ── ──
    │  Each returns {"analysis_results": ["..."]}
    │  operator.add merges all results into MarketingTrendState.analysis_results
    │
    ▼
  synthesize_node                      ← Combines all parallel analysis results
    │                                    into the final intelligence report
    ▼
  END

Key LangGraph patterns used
───────────────────────────
1. Send API (langgraph.types.Send) — used TWICE for dynamic parallel fan-out.
   Phase 1: dispatch_to_sources() → [Send("fetch_source_node", {...})] × N
   Phase 2: dispatch_to_analysis_tools() → [Send("run_analysis_tool_node", {...})] × M
   LangGraph executes all Sends in each phase concurrently in the same superstep.

2. Annotated[list[T], operator.add] reducers
   Phase 1: raw_data — all fetch_source_node calls append without conflict.
   Phase 2: analysis_results — all run_analysis_tool_node calls append without conflict.

3. add_conditional_edges with target node name(s) in a list
   Required to make the Send API work: the graph must know the target node
   is a valid destination for conditional routing.

Usage example
─────────────
  from src.graphs.marketing_trend_graph import marketing_trend_graph

  result = marketing_trend_graph.invoke({
      "messages": [],
      "brand": "Notion",
      "category": "B2B SaaS productivity / knowledge management",
      "query": "What are Notion's competitors spending on ads and what trending narratives should we capitalise on?",
      "sources": [],
      "raw_data": [],
      "analysis_tasks": [],
      "analysis_results": [],
      "analysis_report": "",
  })

  print(result["analysis_report"])
"""

from langgraph.graph import StateGraph, START, END

from src.states.marketing_trend_state import MarketingTrendState
from src.nodes.marketing_trend_node import (
    analysis_dispatcher_node,
    dispatch_to_analysis_tools,
    dispatch_to_sources,
    fetch_source_node,
    orchestrator_node,
    run_analysis_tool_node,
    synthesize_node,
)

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
builder = StateGraph(MarketingTrendState)

# ── Nodes ──────────────────────────────────────────────────────────────────

# Phase 1: orchestrator decides sources, fetch node collects data in parallel
builder.add_node("orchestrator_node", orchestrator_node)
builder.add_node("fetch_source_node", fetch_source_node)

# Phase 2: dispatcher partitions data, analysis tools run in parallel, synthesize fans in
builder.add_node("analysis_dispatcher_node", analysis_dispatcher_node)
builder.add_node("run_analysis_tool_node", run_analysis_tool_node)
builder.add_node("synthesize_node", synthesize_node)

# ── Edges ──────────────────────────────────────────────────────────────────

# Entry: START → orchestrator
builder.add_edge(START, "orchestrator_node")

# Phase 1 dynamic parallel fan-out:
# orchestrator → [Send("fetch_source_node", {...}) × N sources]
builder.add_conditional_edges(
    "orchestrator_node",
    dispatch_to_sources,
    ["fetch_source_node"],
)

# Phase 1 fan-in: all fetch_source_node completions → analysis_dispatcher_node
# LangGraph waits for ALL parallel Sends to complete before moving forward.
builder.add_edge("fetch_source_node", "analysis_dispatcher_node")

# Phase 2 dynamic parallel fan-out:
# dispatcher → [Send("run_analysis_tool_node", {...}) × M tools]
builder.add_conditional_edges(
    "analysis_dispatcher_node",
    dispatch_to_analysis_tools,
    ["run_analysis_tool_node"],
)

# Phase 2 fan-in: all run_analysis_tool_node completions → synthesize_node
# LangGraph waits for ALL parallel analysis Sends to complete before synthesising.
builder.add_edge("run_analysis_tool_node", "synthesize_node")

# Final edge: synthesize → END
builder.add_edge("synthesize_node", END)

# ── Compile ────────────────────────────────────────────────────────────────
marketing_trend_graph = builder.compile()
