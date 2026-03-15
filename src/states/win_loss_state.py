"""
Win/Loss State — State definitions for the Win/Loss Intelligence Agent graph.

Three TypedDicts are defined:

  WinLossState
    The primary graph state shared across all nodes.  Uses operator.add as
    the reducer for raw_signals and extracted_signals so that parallel tasks
    append their results without conflicts.

  SignalFetchTaskState
    A lightweight per-task state sent to wl_fetch_node via the LangGraph
    Send API.  It carries only what one fetch task needs plus a "source" key
    that tells the node which buyer-signal source to query.

    IMPORTANT: SignalFetchTaskState fields that exist in WinLossState use
    compatible types so that the outputs of wl_fetch_node (returned as
    {"raw_signals": [...]}) are merged into the parent graph state correctly
    by LangGraph's state reducers.

  ExtractionTaskState
    A lightweight per-task state sent to wl_extract_node via the LangGraph
    Send API (Phase 2 parallel fan-out).  Each task carries a pre-serialised
    slice of raw signal data and the source label it came from.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Data-source identifiers (used as the "source" field in SignalFetchTaskState)
# ---------------------------------------------------------------------------
# fmt: off
AVAILABLE_SIGNAL_SOURCES = [
    "reddit",              # Buyer complaints and product discussions
    "hn",                  # Hacker News — developer/technical buyer signal
    "google_news",         # Editorial coverage and competitive press
    "g2_reviews",          # G2 structured user reviews
    "capterra_reviews",    # Capterra user reviews
    "linkedin_comments",   # Professional buyer perspective
    "youtube_comments",    # Product perception and adoption barriers
    "trustpilot",          # Trust and NPS signals
    "app_store",           # Apple App Store reviews (mobile products)
    "play_store",          # Google Play Store reviews (mobile products)
]
# fmt: on


# ---------------------------------------------------------------------------
# WinLossState — main graph state
# ---------------------------------------------------------------------------
class WinLossState(TypedDict):
    """Primary state for the Win/Loss Intelligence Agent graph.

    Attributes:
        messages:
            LangChain message history.  Uses add_messages reducer (append-only).

        brand:
            Brand or product name being researched
            (e.g. "Notion", "Linear", "HubSpot").

        category:
            Business category / vertical for context
            (e.g. "B2B SaaS project management", "CRM").

        competitors:
            Optional list of competitor names to include in signal queries
            (e.g. ["Asana", "Monday.com"]).

        query:
            Free-text research question that shapes what the orchestrator
            fetches and what the synthesiser produces
            (e.g. "Why do customers choose us over Asana, and where do we lose deals?").

        sources:
            List of source identifiers (from AVAILABLE_SIGNAL_SOURCES) the
            orchestrator selected for this run.

        raw_signals:
            Accumulated raw results from all parallel fetch tasks.
            Each element is a dict:
              {
                "source":     str,         — which source produced this entry
                "data":       dict | list, — raw API / scrape payload
                "error":      str | None,  — per-source error
                "fetched_at": str,         — ISO timestamp
              }
            Uses operator.add reducer so each wl_fetch_node appends
            without overwriting parallel results.

        extraction_tasks:
            List of extraction task descriptors built by wl_signal_extractor_node.
            Each entry is a dict with keys: brand, category, competitors, query,
            source_label, raw_data_json.

        extracted_signals:
            Accumulated structured signal strings from all parallel
            wl_extract_node invocations.  Uses operator.add so each node
            appends its result without overwriting parallel results.

        signal_matrix:
            Structured Win/Loss Signal Matrix (markdown table + JSON).
            Produced by wl_synthesizer_node.

        win_loss_report:
            Final synthesised executive Win/Loss Intelligence report.
    """

    messages: Annotated[list, add_messages]
    brand: str
    category: str
    competitors: list[str]
    query: str
    sources: list[str]
    raw_signals: Annotated[list[dict], operator.add]
    extraction_tasks: list[dict]
    extracted_signals: Annotated[list[str], operator.add]
    signal_matrix: str
    win_loss_report: str


# ---------------------------------------------------------------------------
# SignalFetchTaskState — per-task state for the Phase 1 Send API fan-out
# ---------------------------------------------------------------------------
class SignalFetchTaskState(TypedDict):
    """Minimal state passed to wl_fetch_node via LangGraph Send API.

    The "source" field determines which data-source utility is called.
    The remaining fields provide context for building the right query.

    Attributes:
        brand:       Brand / product name.
        category:    Business category.
        competitors: List of competitor names.
        query:       Research question for tailoring the fetch.
        source:      One of AVAILABLE_SIGNAL_SOURCES — routes to the correct utility.
        limit:       Max results to request from the data source.
        raw_signals: Field present so LangGraph can merge outputs back into
                     WinLossState.raw_signals via operator.add.
    """

    brand: str
    category: str
    competitors: list[str]
    query: str
    source: str
    limit: int
    raw_signals: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# ExtractionTaskState — per-task state for the Phase 2 Send API fan-out
# ---------------------------------------------------------------------------
class ExtractionTaskState(TypedDict):
    """Minimal state passed to wl_extract_node via LangGraph Send API.

    The "source_label" field identifies which signal source this task
    processes.  "raw_data_json" carries a pre-serialised JSON slice.

    The extracted_signals field mirrors WinLossState.extracted_signals
    so LangGraph can merge node outputs back via the operator.add reducer.

    Attributes:
        brand:             Brand / product name.
        category:          Business category.
        competitors:       Competitor names.
        query:             Research question.
        source_label:      Source identifier string (e.g. "g2_reviews").
        raw_data_json:     Pre-serialised JSON string slice for this source.
        extracted_signals: Fan-in field — node appends its result here so
                           LangGraph merges it into WinLossState.extracted_signals.
    """

    brand: str
    category: str
    competitors: list[str]
    query: str
    source_label: str
    raw_data_json: str
    extracted_signals: Annotated[list[str], operator.add]
