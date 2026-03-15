"""
Marketing Trend State — State definitions for the Marketing & Trend Agent graph.

Three TypedDicts are defined:

  MarketingTrendState
    The primary graph state shared across all nodes.  Uses operator.add as
    the reducer for raw_data and analysis_results so that parallel tasks
    append their results without conflicts.

  FetchTaskState
    A lightweight per-task state sent to fetch_source_node via the LangGraph
    Send API.  It carries only what one fetch task needs plus a "source" key
    that tells the node which data source to query.

    IMPORTANT: FetchTaskState fields that exist in MarketingTrendState use
    compatible types so that the outputs of fetch_source_node (returned as
    {"raw_data": [...]}) are merged into the parent graph state correctly
    by LangGraph's state reducers.

  AnalysisTaskState
    A lightweight per-task state sent to run_analysis_tool_node via the
    LangGraph Send API (Phase 2 parallel fan-out).  Each task encodes a
    single analysis tool call (ad analysis, trend analysis, or patent
    analysis) together with the pre-serialised raw data slice it needs.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Data-source identifiers (used as the "source" field in FetchTaskState)
# ---------------------------------------------------------------------------
# fmt: off
AVAILABLE_SOURCES = [
    "meta_ads",            # Meta Ad Library API  — political + EU ads, demographics
    "google_ads_transparency",  # SerpAPI → Google Ads Transparency Center
    "google_trends",       # SerpAPI → Google Trends (interest-over-time, rising)
    "google_news",         # SerpAPI → Google News (recent editorial coverage)
    "google_search_ads",   # SerpAPI → live paid SERP ad copy
    "linkedin_ads",        # LinkedIn Ad Library via Firecrawl / Playwright fallback
    "reddit",              # Reddit public JSON API + optional OAuth2
    "hn",                  # Hacker News via Algolia full-text search
    "patents",             # USPTO PatentsView API (no key required)
]
# fmt: on


# ---------------------------------------------------------------------------
# MarketingTrendState — main graph state
# ---------------------------------------------------------------------------
class MarketingTrendState(TypedDict):
    """Primary state for the Marketing & Trend Agent graph.

    Attributes:
        messages:
            LangChain message history for the analyst ReAct loop.
            Uses add_messages reducer (append-only).

        brand:
            Brand or advertiser name being researched
            (e.g. "Notion", "Linear", "Figma").

        category:
            Business category / vertical for context
            (e.g. "B2B SaaS project management", "design tools").

        query:
            Free-text research question that shapes what the orchestrator
            fetches and what the analyst synthesises
            (e.g. "What are our top 3 competitors spending on ads this quarter?").

        sources:
            List of source identifiers (from AVAILABLE_SOURCES) the
            orchestrator selected for this run.  The Send API dispatches one
            fetch_source_node invocation per source.

        raw_data:
            Accumulated raw results from all parallel fetch tasks.
            Each element is a dict:
              {
                "source":  str,         — which source produced this entry
                "data":    dict | list, — raw API / scrape payload
                "error":   str | None,  — per-source error
                "fetched_at": str,      — ISO timestamp
              }
            Uses operator.add reducer so each fetch_source_node appends
            without overwriting parallel results.

        analysis_tasks:
            List of analysis task descriptors built by analysis_dispatcher_node.
            Each entry is a dict with keys: brand, category, query,
            tool_name, raw_data_json.  Set once; not reduced.

        analysis_results:
            Accumulated string outputs from all parallel run_analysis_tool_node
            invocations.  Uses operator.add so each node appends its result
            without overwriting parallel results.

        analysis_report:
            Final synthesised marketing intelligence report produced by
            synthesize_node.
    """

    messages: Annotated[list, add_messages]
    brand: str
    category: str
    query: str
    sources: list[str]
    raw_data: Annotated[list[dict], operator.add]
    analysis_tasks: list[dict]
    analysis_results: Annotated[list[str], operator.add]
    analysis_report: str


# ---------------------------------------------------------------------------
# FetchTaskState — per-task state for the Send API fan-out
# ---------------------------------------------------------------------------
class FetchTaskState(TypedDict):
    """Minimal state passed to fetch_source_node via LangGraph Send API.

    The "source" field determines which data-source utility is called.
    The remaining fields provide context for building the right query.

    Because FetchTaskState is passed as the *input* to fetch_source_node,
    the node only reads these fields.  Its *output* dict ({"raw_data": [...]})
    is merged back into MarketingTrendState by LangGraph's reducers.

    Attributes:
        brand:     Brand / advertiser name.
        category:  Business category.
        query:     Research question for tailoring the fetch.
        source:    One of AVAILABLE_SOURCES — routes to the correct utility.
        country:   ISO-3166-1 alpha-2 country code for geo-filtered sources.
                   Defaults to "US".
        limit:     Max results to request from the data source.
        raw_data:  Field present so LangGraph can merge outputs back into
                   MarketingTrendState.raw_data via operator.add.
    """

    brand: str
    category: str
    query: str
    source: str
    country: str
    limit: int
    raw_data: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# AnalysisTaskState — per-task state for the Phase 2 Send API fan-out
# ---------------------------------------------------------------------------
class AnalysisTaskState(TypedDict):
    """Minimal state passed to run_analysis_tool_node via LangGraph Send API.

    The "tool_name" field routes to the correct analysis function.
    "raw_data_json" carries a pre-serialised JSON slice of raw_data so
    the node does not need to re-partition the full state.

    The analysis_results field mirrors MarketingTrendState.analysis_results
    so LangGraph can merge node outputs back via the operator.add reducer.

    Attributes:
        brand:          Brand / advertiser name.
        category:       Business category.
        query:          Research question.
        tool_name:      One of "ad_analysis" | "trend_analysis" | "patent_analysis".
        raw_data_json:  Pre-serialised JSON string slice for this tool.
        analysis_results:
                        Fan-in field — node appends its result here so
                        LangGraph merges it into MarketingTrendState.analysis_results.
    """

    brand: str
    category: str
    query: str
    tool_name: str
    raw_data_json: str
    analysis_results: Annotated[list[str], operator.add]
