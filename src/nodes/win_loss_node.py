"""
Win/Loss Node — Nodes for the Win/Loss Intelligence Agent.

Graph flow implemented here:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                         win_loss_graph                                   │
  │                                                                          │
  │  START                                                                   │
  │    │                                                                     │
  │    ▼                                                                     │
  │  wl_orchestrator_node        Decides which buyer-signal sources to query  │
  │    │                         and builds the list of Send tasks.          │
  │    │  [conditional_edges → dispatch_to_signal_sources]                   │
  │    │                                                                     │
  │    ▼  (DYNAMIC PARALLEL FAN-OUT via LangGraph Send API)                  │
  │  ┌──────────────────────────────────────────────────────────┐            │
  │  │ wl_fetch_node   wl_fetch_node   wl_fetch_node  ...       │            │
  │  │  src=reddit      src=g2          src=capterra             │            │
  │  └──────────────────────────────────────────────────────────┘            │
  │    │   (each returns {"raw_signals": [...]}, merged via operator.add)    │
  │    ▼                                                                     │
  │  wl_signal_extractor_node    Partitions raw_signals by source into       │
  │    │                         extraction_tasks list.                      │
  │    │  [conditional_edges → dispatch_to_extractors]                       │
  │    │                                                                     │
  │    ▼  (DYNAMIC PARALLEL FAN-OUT via LangGraph Send API)                  │
  │  ┌───────────────────────────────────────────────────────────┐           │
  │  │ wl_extract_node   wl_extract_node   wl_extract_node  ...  │           │
  │  │  src=reddit        src=g2            src=capterra          │           │
  │  └───────────────────────────────────────────────────────────┘           │
  │    │   (each returns {"extracted_signals": ["..."]},                     │
  │    │    merged via operator.add into WinLossState)                       │
  │    ▼                                                                     │
  │  wl_synthesizer_node         Builds Win/Loss Signal Matrix +             │
  │    │                         confidence scores + executive report.       │
  │    ▼                                                                     │
  │   END                                                                    │
  └──────────────────────────────────────────────────────────────────────────┘

Key design choices
------------------
* Phase 1 dynamic parallelism: wl_orchestrator_node returns a list of signal-
  source names; dispatch_to_signal_sources() converts those into
  [Send("wl_fetch_node", {...})] objects.  LangGraph executes all Sends
  concurrently.

* Phase 2 dynamic parallelism: wl_signal_extractor_node partitions raw_signals
  by source and builds extraction_tasks; dispatch_to_extractors() converts
  those into [Send("wl_extract_node", {...})] objects.  LangGraph executes all
  per-source extraction tasks concurrently in the same superstep.

* Single polymorphic fetch node: wl_fetch_node reads state["source"] and
  routes to the correct utility.  Returns {"raw_signals": [result_dict]}
  which LangGraph merges via operator.add.

* Single polymorphic extract node: wl_extract_node reads state["source_label"]
  and runs an LLM extraction prompt tuned to that source type.  Returns
  {"extracted_signals": ["[SOURCE_LABEL]\\n..."]} which LangGraph merges via
  operator.add.

* wl_synthesizer_node reads state["extracted_signals"] (the full fan-in list)
  and builds the Win/Loss Signal Matrix, confidence scores, and executive report.
"""

from __future__ import annotations

import json
import datetime
from typing import Any

from langgraph.types import Send

from src.llms.groqllm import GroqLLM
from src.states.win_loss_state import (
    AVAILABLE_SIGNAL_SOURCES,
    SignalFetchTaskState,
    WinLossState,
    ExtractionTaskState,
)
from src.utils.persistence_utils import persist_graph_run

# ---------------------------------------------------------------------------
# Data-source utilities
# ---------------------------------------------------------------------------
from src.utils.reddit_hn_utils import fetch_reddit_posts, fetch_hn_stories
from src.utils.serpapi_utils import google_news
from src.utils.review_scraper_utils import (
    scrape_g2_reviews,
    scrape_capterra_reviews,
    scrape_trustpilot_reviews,
    fetch_youtube_comments,
    fetch_app_store_reviews,
    fetch_play_store_reviews,
    fetch_linkedin_comments,
)


# ===========================================================================
# PHASE 1: Orchestrator Node
# ===========================================================================
def wl_orchestrator_node(state: WinLossState) -> dict:
    """Decide which buyer-signal sources to query based on brand, category, and query.

    The LLM is consulted to pick the most relevant sources — making the
    source selection dynamic and context-aware.

    Returns a state update with "sources" set to the chosen list.
    """
    llm = GroqLLM().get_llm(temperature=0.0)

    brand = state.get("brand", "")
    category = state.get("category", "")
    competitors = state.get("competitors", [])
    query = state.get("query", "")

    competitor_str = (
        f"Competitors to analyse: {', '.join(competitors)}"
        if competitors
        else "No competitors specified."
    )

    system = (
        "You are a win/loss research orchestrator for a competitive intelligence system. "
        "Given a brand, category, competitors, and research query, select the most relevant "
        "buyer-signal sources to query in parallel.\n\n"
        f"Brand: {brand}\n"
        f"Category: {category}\n"
        f"{competitor_str}\n"
        f"Research query: {query}\n\n"
        "Available signal sources (IDs):\n"
        + "\n".join(f"  - {s}" for s in AVAILABLE_SIGNAL_SOURCES)
        + "\n\n"
        "Rules:\n"
        "1. Always include reddit, hn, google_news, and g2_reviews for any query.\n"
        "2. Include capterra_reviews and trustpilot for B2B SaaS or software products.\n"
        "3. Include linkedin_comments for B2B brands or enterprise deals.\n"
        "4. Include youtube_comments when the query concerns product perception or awareness.\n"
        "5. Include app_store and play_store ONLY if the product has a mobile app.\n"
        "6. Respond ONLY with a JSON array of source IDs, e.g.: "
        '["reddit","hn","google_news","g2_reviews","capterra_reviews"]\n'
        "Do not include any other text."
    )

    try:
        response = llm.invoke(system)
        content = (
            str(response.content) if hasattr(response, "content") else str(response)
        )
        content = content.strip().strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
        selected: list[str] = json.loads(content)
        selected = [s for s in selected if s in AVAILABLE_SIGNAL_SOURCES]
    except Exception:
        selected = ["reddit", "hn", "google_news", "g2_reviews", "capterra_reviews"]

    if not selected:
        selected = ["reddit", "hn", "google_news", "g2_reviews"]

    return {"sources": selected}


# ===========================================================================
# PHASE 1: Send-API dispatch function (conditional edge)
# ===========================================================================
def dispatch_to_signal_sources(state: WinLossState) -> list[Send]:
    """Convert state["sources"] into a list of parallel Send objects.

    This function is registered as a conditional edge from wl_orchestrator_node.
    LangGraph executes all returned Send objects concurrently, each invoking
    wl_fetch_node with a tailored SignalFetchTaskState.
    """
    return [
        Send(
            "wl_fetch_node",
            {
                "brand": state.get("brand", ""),
                "category": state.get("category", ""),
                "competitors": state.get("competitors", []),
                "query": state.get("query", ""),
                "source": source,
                "limit": 25,
                "raw_signals": [],  # Required by SignalFetchTaskState type
            },
        )
        for source in state.get("sources", [])
    ]


# ===========================================================================
# PHASE 1: Fetch Node (polymorphic — handles every signal source)
# ===========================================================================
def wl_fetch_node(state: dict) -> dict:
    """Fetch buyer signals from one specific source based on state["source"].

    This single node is invoked in parallel for each source in the plan.
    It reads the "source" field and calls the corresponding utility function.

    Returns {"raw_signals": [result_dict]} which LangGraph merges into
    WinLossState.raw_signals via the operator.add reducer.
    """
    source: str = state.get("source", "")
    brand: str = state.get("brand", "")
    competitors: list[str] = state.get("competitors", [])
    query: str = state.get("query", "")
    limit: int = state.get("limit", 25)
    fetched_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Build the full search query to include competitor context
    competitor_context = f" vs {' vs '.join(competitors)}" if competitors else ""
    full_query = f"{brand}{competitor_context} {query}".strip()

    data: Any = None
    error: str | None = None

    try:
        if source == "reddit":
            raw = fetch_reddit_posts(
                query=full_query,
                sort="relevance",
                time_filter="year",
                limit=limit,
            )
            data = raw
            error = raw.get("error")

        elif source == "hn":
            raw = fetch_hn_stories(
                query=full_query,
                limit=limit,
                num_days_back=365,
            )
            data = raw
            error = raw.get("error")

        elif source == "google_news":
            raw = google_news(
                query=full_query,
                recency="qdr:y",
                num=limit,
            )
            data = raw
            error = raw.get("error")

        elif source == "g2_reviews":
            raw = scrape_g2_reviews(product=brand, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "capterra_reviews":
            raw = scrape_capterra_reviews(product=brand, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "trustpilot":
            raw = scrape_trustpilot_reviews(company=brand, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "linkedin_comments":
            raw = fetch_linkedin_comments(query=full_query, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "youtube_comments":
            raw = fetch_youtube_comments(query=full_query, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "app_store":
            raw = fetch_app_store_reviews(app_name=brand, limit=limit)
            data = raw
            error = raw.get("error")

        elif source == "play_store":
            raw = fetch_play_store_reviews(app_name=brand, limit=limit)
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
    return {"raw_signals": [result]}


# ===========================================================================
# PHASE 2: Signal Extractor Node (fan-in from Phase 1 / fan-out for Phase 2)
# ===========================================================================
def _safe_json(obj: Any, max_chars: int = 8000) -> str:
    """Serialise obj to JSON, truncating at max_chars."""
    try:
        s = json.dumps(obj, default=str)
        return s[:max_chars] + ("..." if len(s) > max_chars else "")
    except Exception:
        return str(obj)[:max_chars]


def wl_signal_extractor_node(state: WinLossState) -> dict:
    """Partition raw_signals by source and build per-source extraction_tasks.

    Reads the accumulated raw_signals from Phase 1, creates one
    ExtractionTaskState descriptor per source that has data, and stores
    them in state["extraction_tasks"] for dispatch_to_extractors().

    Returns {"extraction_tasks": [...], "extracted_signals": []} with one
    task per source that returned non-empty data.
    """
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    competitors: list[str] = state.get("competitors", [])
    query: str = state.get("query", "")
    raw_signals: list[dict] = state.get("raw_signals", [])

    tasks: list[dict] = []

    for signal in raw_signals:
        source_label = signal.get("source", "unknown")
        data = signal.get("data")
        if data is None:
            continue
        tasks.append(
            {
                "brand": brand,
                "category": category,
                "competitors": competitors,
                "query": query,
                "source_label": source_label,
                "raw_data_json": _safe_json(data),
                "extracted_signals": [],
            }
        )

    # Always create at least one task even if all sources errored,
    # so the synthesizer always runs.
    if not tasks:
        tasks.append(
            {
                "brand": brand,
                "category": category,
                "competitors": competitors,
                "query": query,
                "source_label": "fallback",
                "raw_data_json": "[]",
                "extracted_signals": [],
            }
        )

    return {"extraction_tasks": tasks, "extracted_signals": []}


# ===========================================================================
# PHASE 2: Send-API dispatch function (conditional edge)
# ===========================================================================
def dispatch_to_extractors(state: WinLossState) -> list[Send]:
    """Convert state["extraction_tasks"] into a list of parallel Send objects.

    This function is registered as a conditional edge from wl_signal_extractor_node.
    LangGraph executes all returned Send objects concurrently — one
    wl_extract_node per extraction task — in the same superstep.
    """
    return [Send("wl_extract_node", task) for task in state.get("extraction_tasks", [])]


# ===========================================================================
# PHASE 2: Extract Node (polymorphic — extracts win/loss signals per source)
# ===========================================================================
def wl_extract_node(state: dict) -> dict:
    """Run LLM-based win/loss signal extraction for one source.

    Reads state["source_label"] to determine the source type and builds
    an appropriate extraction prompt.  Returns structured win/loss signals
    as a labelled string.

    Returns {"extracted_signals": ["[SOURCE_LABEL]\\n..."]} which LangGraph
    merges into WinLossState.extracted_signals via the operator.add reducer.
    """
    source_label: str = state.get("source_label", "unknown")
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    competitors: list[str] = state.get("competitors", [])
    query: str = state.get("query", "")
    raw_data_json: str = state.get("raw_data_json", "[]")

    competitor_str = (
        ", ".join(competitors) if competitors else "competitors (unspecified)"
    )

    try:
        result = _extract_win_loss_signals(
            brand=brand,
            category=category,
            competitors=competitor_str,
            query=query,
            source_label=source_label,
            raw_data_json=raw_data_json,
        )
    except Exception as exc:
        result = f"Error extracting signals from {source_label}: {exc}"

    return {"extracted_signals": [f"[{source_label.upper()}]\n{result}"]}


# ===========================================================================
# PHASE 2: Plain extraction function (no @tool decorator)
# ===========================================================================
def _extract_win_loss_signals(
    brand: str,
    category: str,
    competitors: str,
    query: str,
    source_label: str,
    raw_data_json: str,
) -> str:
    """Use the LLM to extract structured win/loss signals from one source's data."""
    llm = GroqLLM().get_llm(temperature=0.1)

    source_guidance = _SOURCE_GUIDANCE.get(
        source_label, "Analyse for win/loss signals."
    )

    prompt = (
        f"You are a win/loss analyst extracting structured buyer signals for:\n"
        f"  Brand: {brand}\n"
        f"  Category: {category}\n"
        f"  Competitors: {competitors}\n"
        f"  Research question: {query}\n\n"
        f"Data source: {source_label}\n"
        f"Source guidance: {source_guidance}\n\n"
        f"Raw data (JSON):\n{raw_data_json[:6000]}\n\n"
        "Extract all observable win reasons and loss reasons from this data.\n"
        "Format your output as follows:\n\n"
        "WIN REASONS:\n"
        "- [Reason]: [Evidence quote or paraphrase from the data] (frequency: low/medium/high)\n\n"
        "LOSS REASONS / SWITCH RISKS:\n"
        "- [Reason]: [Evidence quote or paraphrase from the data] (frequency: low/medium/high)\n\n"
        "NEUTRAL OBSERVATIONS:\n"
        "- [Observation]: [Evidence]\n\n"
        "If the data is empty or irrelevant, state 'No win/loss signals found in this source.'\n"
        "Be specific. Quote actual text from the data where possible."
    )

    response = llm.invoke(prompt)
    return str(response.content)


# Source-specific extraction guidance
_SOURCE_GUIDANCE: dict[str, str] = {
    "reddit": (
        "Focus on complaint threads, comparison posts ('X vs Y'), and feature requests. "
        "High-score posts and long comment threads indicate strong signal."
    ),
    "hn": (
        "Focus on technical buyer perspective: performance, scalability, integrations, "
        "pricing complaints, and migration stories."
    ),
    "google_news": (
        "Focus on editorial framing: competitive wins/losses, funding events, "
        "product launches, and analyst commentary."
    ),
    "g2_reviews": (
        "Focus on star ratings, 'What do you like best' and 'What do you dislike' sections. "
        "These are the clearest structured win/loss signals."
    ),
    "capterra_reviews": (
        "Focus on pros/cons sections, 'Reasons for switching', and 'Alternatives considered'. "
        "These directly reveal competitive switching behaviour."
    ),
    "trustpilot": (
        "Focus on NPS tone (promoter vs detractor language), recurring complaints, "
        "and customer service issues that drive churn."
    ),
    "linkedin_comments": (
        "Focus on professional buyer perspective: ROI, implementation difficulty, "
        "enterprise feature gaps, and vendor relationship signals."
    ),
    "youtube_comments": (
        "Focus on tutorial reaction comments, review video comments, and migration "
        "story comments — they reveal real adoption friction."
    ),
    "app_store": (
        "Focus on recent 1-3 star reviews (loss signals) and 4-5 star reviews "
        "(win/retention signals), especially those mentioning competitors."
    ),
    "play_store": (
        "Same as App Store: focus on recent reviews mentioning competitors, "
        "missing features, and usability praise."
    ),
    "fallback": ("No raw data available — note this as a data gap."),
}


# ===========================================================================
# PHASE 2: Confidence Scoring
# ===========================================================================
def _score_signal_confidence(signal_text: str, source_label: str) -> float:
    """Compute a confidence score (0.0–1.0) for a signal based on source credibility
    and signal strength keywords.

    This is a heuristic function — no LLM call needed.
    """
    # Source credibility weights (G2 and Capterra are highest — structured review data)
    source_weights: dict[str, float] = {
        "g2_reviews": 0.9,
        "capterra_reviews": 0.88,
        "trustpilot": 0.80,
        "reddit": 0.72,
        "linkedin_comments": 0.70,
        "app_store": 0.75,
        "play_store": 0.72,
        "hn": 0.65,
        "youtube_comments": 0.60,
        "google_news": 0.65,
        "fallback": 0.10,
    }
    base = source_weights.get(source_label, 0.5)

    # Boost for frequency indicators
    text_lower = signal_text.lower()
    if "frequency: high" in text_lower:
        base = min(1.0, base + 0.08)
    elif "frequency: medium" in text_lower:
        base = min(1.0, base + 0.04)
    elif "frequency: low" in text_lower:
        base = max(0.0, base - 0.04)

    # Penalise if the source returned no signals
    if "no win/loss signals found" in text_lower or "no raw data" in text_lower:
        base = max(0.0, base - 0.4)

    return round(base, 2)


# ===========================================================================
# PHASE 2: Synthesizer Node
# ===========================================================================
def wl_synthesizer_node(state: WinLossState) -> dict:
    """Build the Win/Loss Signal Matrix and final executive report.

    Reads state["extracted_signals"] — the accumulated list of labelled
    signal strings from all wl_extract_node invocations — scores them,
    builds the Signal Matrix, and calls the synthesis LLM for the report.

    Returns {"signal_matrix": "...", "win_loss_report": "..."}.
    """
    brand: str = state.get("brand", "")
    category: str = state.get("category", "")
    competitors: list[str] = state.get("competitors", [])
    query: str = state.get("query", "")
    extracted_signals: list[str] = state.get("extracted_signals", [])

    competitor_str = (
        ", ".join(competitors) if competitors else "unspecified competitors"
    )

    # Parse each labelled signal block and attach confidence scores
    signal_blocks: list[dict] = []
    for sig in extracted_signals:
        if not sig:
            continue
        # Extract label from "[SOURCE_LABEL]\n..."
        if sig.startswith("[") and "]" in sig:
            label_end = sig.index("]")
            source_label = sig[1:label_end].lower()
            content = sig[label_end + 1 :].strip()
        else:
            source_label = "unknown"
            content = sig

        confidence = _score_signal_confidence(content, source_label)
        signal_blocks.append(
            {
                "source": source_label,
                "content": content,
                "confidence": confidence,
            }
        )

    # Build the signal matrix as markdown
    signal_matrix = _build_signal_matrix(signal_blocks, brand)

    # Build the combined signals text for the synthesis LLM
    signals_text = "\n\n".join(
        f"### {b['source'].upper()} (confidence: {b['confidence']})\n{b['content'][:1500]}"
        for b in sorted(signal_blocks, key=lambda x: x["confidence"], reverse=True)
    )

    llm = GroqLLM().get_llm(temperature=0.2)
    prompt = (
        f"You are producing a final Win/Loss Intelligence Report for:\n"
        f"  Brand: {brand}\n"
        f"  Category: {category}\n"
        f"  Competitors analysed: {competitor_str}\n"
        f"  Original Research Question: {query}\n\n"
        "You have the following buyer-signal extractions from multiple sources:\n\n"
        f"{signals_text[:8000] if signals_text else 'No signals were extracted from any source.'}\n\n"
        "---\n\n"
        "Win/Loss Signal Matrix (pre-built for reference):\n"
        f"{signal_matrix[:2000]}\n\n"
        "---\n\n"
        "Produce a concise, executive-level Win/Loss Intelligence Report in markdown with:\n\n"
        "## Executive Summary\n"
        "  - 3–4 bullet points directly answering the research question\n\n"
        "## Top Win Reasons (why customers choose us)\n"
        "  - Each reason with frequency estimate and primary source\n\n"
        "## Top Loss Reasons / Switch Risks (why we lose deals or customers churn)\n"
        "  - Each reason with frequency estimate and primary source\n\n"
        "## Competitive Battlecards\n"
        "  - Per competitor: key differentiators we win on, key vulnerabilities\n\n"
        "## Signal Confidence Assessment\n"
        "  - Rate overall data quality and flag any critical gaps\n\n"
        "## Recommended Actions (3–5 concrete, prioritised next steps)\n"
        "  - Sales enablement, product, marketing, and CS implications\n\n"
        "## Data Sources\n"
        "  - List sources and confidence scores\n\n"
        "Keep the report tight and actionable. Sales and product teams must be able to act on it."
    )

    response = llm.invoke(prompt)
    report = str(response.content)

    final_state = {
        "signal_matrix": signal_matrix,
        "win_loss_report": report,
    }

    # Persist this graph run to ChromaDB
    try:
        persist_graph_run(
            graph_name="win_loss_graph",
            state={**dict(state), **final_state},
            brand=brand,
            category=category,
            query=query,
        )
    except Exception:
        pass  # Never let persistence failure break the graph

    return final_state


def _build_signal_matrix(signal_blocks: list[dict], brand: str) -> str:
    """Build a markdown Win/Loss Signal Matrix table from extracted signal blocks."""
    if not signal_blocks:
        return "| Signal | Type | Frequency | Confidence | Source |\n|--------|------|-----------|------------|--------|\n| No signals extracted | — | — | — | — |"

    rows: list[str] = []
    rows.append("| Signal | Type | Frequency | Confidence | Source |")
    rows.append("|--------|------|-----------|------------|--------|")

    for block in sorted(signal_blocks, key=lambda x: x["confidence"], reverse=True):
        source = block["source"]
        content = block["content"]
        confidence = block["confidence"]

        # Extract win/loss rows from the content block
        lines = content.splitlines()
        current_type = "Neutral"
        for line in lines:
            line = line.strip()
            if "WIN REASONS" in line.upper():
                current_type = "Win"
                continue
            if "LOSS REASONS" in line.upper() or "SWITCH RISKS" in line.upper():
                current_type = "Loss"
                continue
            if "NEUTRAL OBSERVATIONS" in line.upper():
                current_type = "Neutral"
                continue
            if line.startswith("- ") and len(line) > 5:
                signal_text = line[2:].split(":")[0].strip()[:80]
                freq_match = ""
                if "frequency: high" in line.lower():
                    freq_match = "High"
                elif "frequency: medium" in line.lower():
                    freq_match = "Medium"
                elif "frequency: low" in line.lower():
                    freq_match = "Low"
                else:
                    freq_match = "Unknown"
                rows.append(
                    f"| {signal_text} | {current_type} | {freq_match} | {confidence} | {source} |"
                )

    if len(rows) <= 2:
        rows.append(f"| Signals present but unparseable | — | — | — | multiple |")

    return "\n".join(rows)
