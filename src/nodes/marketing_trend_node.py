"""
Marketing Trend Node — Nodes and tools for the Marketing & Trend Agent.

Graph flow implemented here:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                       marketing_trend_graph                              │
  │                                                                          │
  │  START                                                                   │
  │    │                                                                     │
  │    ▼                                                                     │
  │  orchestrator_node           Decides which data sources to query and     │
  │    │                         builds the list of Send tasks.              │
  │    │  [conditional_edges → dispatch_to_sources]                          │
  │    │                                                                     │
  │    ▼  (DYNAMIC PARALLEL FAN-OUT via LangGraph Send API)                  │
  │  ┌──────────────────────────────────────────────────────────┐            │
  │  │ fetch_source_node  fetch_source_node  fetch_source_node  │  ...       │
  │  │  source=meta_ads    source=google_     source=linkedin   │            │
  │  │                         trends                           │            │
  │  └──────────────────────────────────────────────────────────┘            │
  │    │   (each returns {"raw_data": [...]}, merged via operator.add)       │
  │    ▼                                                                     │
  │  analysis_dispatcher_node    Partitions raw_data into three tool slices  │
  │    │                         and builds analysis_tasks list.             │
  │    │  [conditional_edges → dispatch_to_analysis_tools]                   │
  │    │                                                                     │
  │    ▼  (DYNAMIC PARALLEL FAN-OUT via LangGraph Send API)                  │
  │  ┌───────────────────────────────────────────────────────────┐           │
  │  │ run_analysis_tool_node   run_analysis_tool_node           │           │
  │  │  tool=ad_analysis         tool=trend_analysis             │           │
  │  │                                                           │           │
  │  │ run_analysis_tool_node                                    │           │
  │  │  tool=patent_analysis                                     │           │
  │  └───────────────────────────────────────────────────────────┘           │
  │    │   (each returns {"analysis_results": ["..."]},                      │
  │    │    merged via operator.add into MarketingTrendState)                │
  │    ▼                                                                     │
  │  synthesize_node             Combines all parallel analysis results      │
  │    │                         into the final intelligence report.         │
  │    ▼                                                                     │
  │   END                                                                    │
  └──────────────────────────────────────────────────────────────────────────┘

Key design choices
------------------
* Phase 1 dynamic parallelism:  orchestrator_node returns a list of data-source
  names; dispatch_to_sources() converts those into [Send("fetch_source_node", {...})]
  objects.  LangGraph executes all Sends concurrently.

* Phase 2 dynamic parallelism:  analysis_dispatcher_node partitions raw_data
  and builds analysis_tasks; dispatch_to_analysis_tools() converts those into
  [Send("run_analysis_tool_node", {...})] objects.  LangGraph executes all
  three analysis tools concurrently in the same superstep.

* Single polymorphic analysis node:  run_analysis_tool_node reads state["tool_name"]
  and routes to the correct plain Python analysis function.  Returns
  {"analysis_results": ["result string"]} which LangGraph merges via operator.add.

* synthesize_node reads state["analysis_results"] (the full fan-in list) and
  calls synthesize_marketing_intelligence_report() to produce the final report.
"""

from __future__ import annotations

import json
import datetime
from typing import Any

from langgraph.types import Send

from src.llms.groqllm import GroqLLM
from src.states.marketing_trend_state import (
    AVAILABLE_SOURCES,
    FetchTaskState,
    MarketingTrendState,
    AnalysisTaskState,
)

# ---------------------------------------------------------------------------
# Data-source utilities (imported at top level for IDE support)
# ---------------------------------------------------------------------------
from src.utils.meta_ads_utils import fetch_meta_ads_paginated, summarise_meta_ads
from src.utils.serpapi_utils import (
    google_ads_transparency,
    google_news,
    google_search_ads,
    google_trends,
)
from src.utils.linkedin_ads_utils import fetch_linkedin_ads
from src.utils.reddit_hn_utils import fetch_hn_stories, fetch_reddit_posts
from src.utils.patents_utils import get_company_patents, search_patents
from src.utils.persistence_utils import persist_graph_run


# ===========================================================================
# PHASE 1: Orchestrator Node
# ===========================================================================
def orchestrator_node(state: MarketingTrendState) -> dict:
    """Decide which data sources to query based on brand, category, and query.

    The LLM is consulted to pick the most relevant sources — making the
    source selection itself dynamic and context-aware rather than always
    querying every available source.

    Returns a state update with "sources" set to the chosen list.
    """
    llm = GroqLLM().get_llm(temperature=0.0)

    brand = state.get("brand", "")
    category = state.get("category", "")
    query = state.get("query", "")

    system = (
        "You are a research orchestrator for a marketing intelligence system. "
        "Given a brand, category, and research query, select the most relevant "
        "data sources to query in parallel.\n\n"
        f"Brand: {brand}\n"
        f"Category: {category}\n"
        f"Research query: {query}\n\n"
        "Available data sources (IDs):\n"
        + "\n".join(f"  - {s}" for s in AVAILABLE_SOURCES)
        + "\n\n"
        "Rules:\n"
        "1. Always include google_trends, google_news, reddit, and hn for any query.\n"
        "2. Include meta_ads and google_ads_transparency if the brand runs paid ads or if the "
        "   query concerns advertising spend / creatives.\n"
        "3. Include linkedin_ads for B2B brands or if the query is about B2B marketing.\n"
        "4. Include google_search_ads when the query asks about SERP ad copy or keywords.\n"
        "5. Include patents if the query concerns technology, R&D, or technical moats.\n"
        "6. Respond ONLY with a JSON array of source IDs, e.g.: "
        '["google_trends","google_news","reddit","hn","meta_ads"]\n'
        "Do not include any other text."
    )

    try:
        response = llm.invoke(system)
        content = (
            str(response.content) if hasattr(response, "content") else str(response)
        )
        # Strip markdown fences if present
        content = content.strip().strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
        selected: list[str] = json.loads(content)
        # Validate: only allow known sources
        selected = [s for s in selected if s in AVAILABLE_SOURCES]
    except Exception:
        # Fallback: safe default set
        selected = ["google_trends", "google_news", "reddit", "hn", "meta_ads"]

    if not selected:
        selected = ["google_trends", "google_news", "reddit", "hn"]

    return {"sources": selected}


# ===========================================================================
# PHASE 1: Send-API dispatch function (conditional edge)
# ===========================================================================
def dispatch_to_sources(state: MarketingTrendState) -> list[Send]:
    """Convert state["sources"] into a list of parallel Send objects.

    This function is registered as a conditional edge from orchestrator_node.
    LangGraph executes all returned Send objects concurrently, each invoking
    fetch_source_node with a tailored FetchTaskState.

    This is the core of the dynamic parallelism: the number of parallel
    branches (and which sources they hit) is decided at runtime.
    """
    return [
        Send(
            "fetch_source_node",
            {
                "brand": state.get("brand", ""),
                "category": state.get("category", ""),
                "query": state.get("query", ""),
                "source": source,
                "country": "US",
                "limit": 25,
                "raw_data": [],  # Required by FetchTaskState type
            },
        )
        for source in state.get("sources", [])
    ]


# ===========================================================================
# PHASE 1: Fetch Source Node (polymorphic — handles every source)
# ===========================================================================
def fetch_source_node(state: dict) -> dict:
    """Fetch data from one specific source based on state["source"].

    This single node is invoked in parallel for each source in the plan.
    It reads the "source" field and calls the corresponding utility function.

    Returns {"raw_data": [result_dict]} which LangGraph merges into
    MarketingTrendState.raw_data via the operator.add reducer.
    """
    source: str = state.get("source", "")
    brand: str = state.get("brand", "")
    query: str = state.get("query", "")
    country: str = state.get("country", "US")
    limit: int = state.get("limit", 25)
    fetched_at = datetime.datetime.utcnow().isoformat() + "Z"

    data: Any = None
    error: str | None = None

    try:
        if source == "meta_ads":
            raw = fetch_meta_ads_paginated(
                search_terms=brand,
                country_codes=[country],
                ad_type="ALL",
                limit_per_page=min(limit, 50),
                max_pages=2,
            )
            data = {
                "summary": summarise_meta_ads(raw.get("ads", [])),
                "sample_ads": raw.get("ads", [])[:10],
                "pages_fetched": raw.get("pages_fetched", 0),
            }
            error = raw.get("error")

        elif source == "google_ads_transparency":
            raw = google_ads_transparency(advertiser=brand, region=country, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "google_trends":
            raw = google_trends(
                keywords=[brand, query] if query and query != brand else [brand],
                timeframe="today 12-m",
                geo=country,
            )
            data = raw
            error = raw.get("error")

        elif source == "google_news":
            raw = google_news(
                query=f"{brand} {query}".strip(), recency="qdr:m", num=limit
            )
            data = raw
            error = raw.get("error")

        elif source == "google_search_ads":
            raw = google_search_ads(
                query=f"{brand} {query}".strip(), num=limit, country=country.lower()
            )
            data = raw
            error = raw.get("error")

        elif source == "linkedin_ads":
            raw = fetch_linkedin_ads(advertiser=brand, date_range="pastMonth")
            data = raw
            error = raw.get("error")

        elif source == "reddit":
            raw = fetch_reddit_posts(
                query=f"{brand} {query}".strip(),
                sort="relevance",
                time_filter="month",
                limit=limit,
            )
            data = raw
            error = raw.get("error")

        elif source == "hn":
            raw = fetch_hn_stories(
                query=f"{brand} {query}".strip(),
                limit=limit,
                num_days_back=90,
            )
            data = raw
            error = raw.get("error")

        elif source == "patents":
            raw = get_company_patents(company=brand, years_back=3, limit=limit)
            data = raw
            error = raw.get("error")

        else:
            error = f"Unknown source: '{source}'"

    except Exception as exc:
        error = str(exc)

    result = {
        "source": source,
        "brand": brand,
        "data": data,
        "error": error,
        "fetched_at": fetched_at,
    }
    return {"raw_data": [result]}


# ===========================================================================
# PHASE 2: Analysis Dispatcher Node
# ===========================================================================

# Source-type groupings used to partition raw_data
_AD_SOURCES = {
    "meta_ads",
    "google_ads_transparency",
    "linkedin_ads",
    "google_search_ads",
}
_TREND_SOURCES = {"google_trends", "google_news", "reddit", "hn"}
_TECH_SOURCES = {"patents"}


def _safe_json(obj: Any, max_chars: int = 6000) -> str:
    """Serialise obj to JSON, truncating at max_chars."""
    try:
        s = json.dumps(obj, default=str)
        return s[:max_chars] + ("..." if len(s) > max_chars else "")
    except Exception:
        return str(obj)[:max_chars]


def analysis_dispatcher_node(state: MarketingTrendState) -> dict:
    """Partition raw_data and build the analysis_tasks list.

    Reads the accumulated raw_data from Phase 1, partitions entries by
    source type (ad / trend / tech), and creates one AnalysisTaskState
    descriptor per non-empty partition.  The descriptors are stored in
    state["analysis_tasks"] so dispatch_to_analysis_tools() can read them.

    Returns {"analysis_tasks": [...]} with zero, one, two, or three tasks
    depending on which partitions have data.
    """
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    query: str = state.get("query", "")
    raw_data: list[dict] = state.get("raw_data", [])

    ad_data = [r for r in raw_data if r.get("source") in _AD_SOURCES]
    trend_data = [r for r in raw_data if r.get("source") in _TREND_SOURCES]
    tech_data = [r for r in raw_data if r.get("source") in _TECH_SOURCES]

    tasks: list[dict] = []

    # Always include ad and trend tasks (even if data is empty — the analysis
    # function will still produce a "no data available" note, which is useful).
    tasks.append(
        {
            "brand": brand,
            "category": category,
            "query": query,
            "tool_name": "ad_analysis",
            "raw_data_json": _safe_json(ad_data),
            "analysis_results": [],
        }
    )
    tasks.append(
        {
            "brand": brand,
            "category": category,
            "query": query,
            "tool_name": "trend_analysis",
            "raw_data_json": _safe_json(trend_data),
            "analysis_results": [],
        }
    )

    # Only include patent task if we actually have patent data
    if tech_data:
        tasks.append(
            {
                "brand": brand,
                "category": category,
                "query": query,
                "tool_name": "patent_analysis",
                "raw_data_json": _safe_json(tech_data),
                "analysis_results": [],
            }
        )

    return {"analysis_tasks": tasks, "analysis_results": []}


# ===========================================================================
# PHASE 2: Send-API dispatch function (conditional edge)
# ===========================================================================
def dispatch_to_analysis_tools(state: MarketingTrendState) -> list[Send]:
    """Convert state["analysis_tasks"] into a list of parallel Send objects.

    This function is registered as a conditional edge from analysis_dispatcher_node.
    LangGraph executes all returned Send objects concurrently — one
    run_analysis_tool_node per analysis task — in the same superstep.
    """
    return [
        Send("run_analysis_tool_node", task) for task in state.get("analysis_tasks", [])
    ]


# ===========================================================================
# PHASE 2: Run Analysis Tool Node (polymorphic — handles every tool type)
# ===========================================================================
def run_analysis_tool_node(state: dict) -> dict:
    """Run one analysis tool based on state["tool_name"].

    This single node is invoked in parallel for each analysis task.
    It reads the "tool_name" field and calls the corresponding plain
    Python analysis function.

    Returns {"analysis_results": ["result string"]} which LangGraph merges
    into MarketingTrendState.analysis_results via the operator.add reducer.

    The result string is prefixed with a label so synthesize_node can
    identify which analysis produced which output.
    """
    tool_name: str = state.get("tool_name", "")
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    raw_data_json: str = state.get("raw_data_json", "[]")

    try:
        if tool_name == "ad_analysis":
            result = _analyze_ad_spend_and_creatives(
                brand=brand, raw_data_json=raw_data_json
            )
            label = "AD_ANALYSIS"
        elif tool_name == "trend_analysis":
            result = _analyze_trend_signals(brand=brand, raw_data_json=raw_data_json)
            label = "TREND_ANALYSIS"
        elif tool_name == "patent_analysis":
            result = _analyze_technical_and_patent_landscape(
                brand=brand, raw_data_json=raw_data_json
            )
            label = "PATENT_ANALYSIS"
        else:
            result = f"Unknown tool_name: '{tool_name}'"
            label = "ERROR"
    except Exception as exc:
        result = f"Error in {tool_name}: {exc}"
        label = "ERROR"

    return {"analysis_results": [f"[{label}]\n{result}"]}


# ===========================================================================
# PHASE 2: Plain analysis functions (no @tool decorator)
# ===========================================================================


def _analyze_ad_spend_and_creatives(brand: str, raw_data_json: str) -> str:
    """Analyse paid advertising spend, creative strategy, and channel mix."""
    llm = GroqLLM().get_llm(temperature=0.1)
    prompt = (
        f"You are analysing paid advertising intelligence for brand: '{brand}'.\n\n"
        f"Raw ad data (JSON):\n{raw_data_json[:6000]}\n\n"
        "Provide a structured analysis covering:\n"
        "1. **Spend & Scale**: estimated spend ranges, impression volumes, active vs stopped ads.\n"
        "2. **Creative Themes**: dominant messaging angles, emotional hooks, unique value propositions.\n"
        "3. **Channel Strategy**: which ad platforms are used and to what degree.\n"
        "4. **Targeting Signals**: demographic skews, geographic focus, audience segments.\n"
        "5. **CTA Patterns**: most common calls-to-action and landing page destinations.\n"
        "6. **Competitive Gaps**: messaging angles the brand is NOT using but competitors are.\n"
        "Be specific with data. Call out numbers and examples from the raw data."
    )
    response = llm.invoke(prompt)
    return str(response.content)


def _analyze_trend_signals(brand: str, raw_data_json: str) -> str:
    """Identify trend signals from Google Trends, News, Reddit, and Hacker News."""
    llm = GroqLLM().get_llm(temperature=0.15)
    prompt = (
        f"You are analysing market trend signals for brand/topic: '{brand}'.\n\n"
        f"Raw trend data (JSON):\n{raw_data_json[:6000]}\n\n"
        "Provide a structured analysis covering:\n"
        "1. **Search Momentum**: is interest in this brand/category growing, peaking, or declining?\n"
        "   Include specific trend values/dates if available.\n"
        "2. **Rising Queries**: which adjacent keywords are gaining traction?\n"
        "3. **Editorial Narrative**: key themes in news coverage over the past month.\n"
        "4. **Community Sentiment**: Reddit and HN tone — excitement, frustration, curiosity?\n"
        "   Include top post titles and scores as evidence.\n"
        "5. **Emerging Narratives**: new angles or use-cases being discussed that weren't mainstream.\n"
        "6. **Signal Strength**: rate the overall market momentum (1–10) with justification.\n"
        "Ground every point in the data. Quote post titles, trend values, article headlines."
    )
    response = llm.invoke(prompt)
    return str(response.content)


def _analyze_technical_and_patent_landscape(brand: str, raw_data_json: str) -> str:
    """Analyse the technology and IP landscape via patent filings."""
    llm = GroqLLM().get_llm(temperature=0.1)
    prompt = (
        f"You are analysing the technology and IP landscape for company: '{brand}'.\n\n"
        f"Raw patent data (JSON):\n{raw_data_json[:6000]}\n\n"
        "Provide a structured analysis covering:\n"
        "1. **R&D Focus Areas**: dominant CPC codes and what technology areas they represent.\n"
        "2. **Filing Velocity**: patent filing cadence — increasing/decreasing/stable?\n"
        "3. **Technology Moats**: any uniquely broad or defensible patents?\n"
        "4. **Key Inventors**: prolific inventors and their apparent research themes.\n"
        "5. **Pre-Launch Signals**: patents filed in the last 12–18 months that hint at "
        "   unreleased products or features.\n"
        "6. **Competitive IP Risk**: overlaps with your category that could present "
        "   licensing threats or partnership opportunities.\n"
        "Be specific. Reference patent titles and filing dates as evidence."
    )
    response = llm.invoke(prompt)
    return str(response.content)


# ===========================================================================
# PHASE 2: Synthesize Node (fan-in — reads all parallel analysis results)
# ===========================================================================


def synthesize_node(state: MarketingTrendState) -> dict:
    """Combine all parallel analysis results into a final intelligence report.

    Reads state["analysis_results"] — the accumulated list of labelled
    analysis strings from all run_analysis_tool_node invocations — and
    calls the synthesis LLM to produce the final structured report.

    Returns {"analysis_report": "..."}.
    """
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    query: str = state.get("query", "")
    analysis_results: list[str] = state.get("analysis_results", [])

    # Parse labelled results
    ad_analysis = ""
    trend_analysis = ""
    patent_analysis = ""

    for result in analysis_results:
        if result.startswith("[AD_ANALYSIS]"):
            ad_analysis = result[len("[AD_ANALYSIS]") :].strip()
        elif result.startswith("[TREND_ANALYSIS]"):
            trend_analysis = result[len("[TREND_ANALYSIS]") :].strip()
        elif result.startswith("[PATENT_ANALYSIS]"):
            patent_analysis = result[len("[PATENT_ANALYSIS]") :].strip()

    llm = GroqLLM().get_llm(temperature=0.2)
    prompt = (
        f"You are producing a final Marketing Intelligence Report for:\n"
        f"  Brand: {brand}\n"
        f"  Category: {category}\n"
        f"  Original Research Question: {query}\n\n"
        "You have the following specialist analyses available:\n\n"
        "## Ad Spend & Creative Intelligence\n"
        f"{ad_analysis[:2500] if ad_analysis else 'No ad data was collected.'}\n\n"
        "## Market Trend Signals\n"
        f"{trend_analysis[:2500] if trend_analysis else 'No trend data was collected.'}\n\n"
        "## Technical & Patent Landscape\n"
        f"{patent_analysis[:1500] if patent_analysis else 'No patent data was collected (not requested for this query).'}\n\n"
        "---\n\n"
        "Produce a concise, executive-level Marketing Intelligence Report in markdown with:\n\n"
        "## Executive Summary (3–4 bullet points answering the original question)\n\n"
        "## Ad Strategy Intelligence\n"
        "  - Key findings on competitor ad spend, creatives, channels\n"
        "  - Opportunities to differentiate messaging\n\n"
        "## Market Momentum & Trend Analysis\n"
        "  - Current momentum trajectory\n"
        "  - Rising narratives to capitalise on\n"
        "  - Community sentiment summary\n\n"
        "## Technical Signals (if relevant)\n"
        "  - R&D directions, pre-launch hints, IP landscape\n\n"
        "## Recommended Actions (3–5 concrete, prioritised next steps)\n\n"
        "## Data Sources & Confidence\n"
        "  - List which sources returned data and flag any gaps\n\n"
        "Keep the report tight and actionable. Marketing teams should be able to act on it."
    )
    response = llm.invoke(prompt)
    analysis_report = str(response.content)

    final_state = {"analysis_report": analysis_report}

    # Persist this graph run to ChromaDB
    try:
        persist_graph_run(
            graph_name="marketing_trend_graph",
            state={**dict(state), **final_state},
            brand=brand,
            category=category,
            query=query,
        )
    except Exception:
        pass  # Never let persistence failure break the graph

    return final_state
