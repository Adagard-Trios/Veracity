"""
Competitor Node — Three-stage parallel pipeline for live competitive intelligence.

Architecture:
    planner_node          — LLM identifies competitors → emits Send objects
    competitor_fetch_node — one parallel branch per competitor; all 3 Firecrawl
                            calls run concurrently via ThreadPoolExecutor
    compiler_node         — aggregates all parallel results → CompetitivePayload

The old single agent_node (ReAct tool-calling loop) is fully replaced.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Send
from src.llms.groqllm import GroqLLM
from src.nodes.competitor_schemas import (
    CompetitivePayload,
    CompetitorTask,
)
from src.nodes.competitor_tools import (
    fetch_competitor_website,
    fetch_competitor_changelog,
    fetch_producthunt_launches,
)


# ---------------------------------------------------------------------------
# Stage 1 — Planner node
# ---------------------------------------------------------------------------

PLANNER_SYSTEM = """You are a Competitive Intelligence Planner. \
Your sole job is to read the provided pre-fetched content and return a \
JSON array of competitor objects to research.

Output ONLY valid JSON — no preamble, no markdown fences. Schema:

[
  {
    "name": "Competitor display name",
    "website_url": "https://...",
    "changelog_url": "https://.../changelog"
  }
]

Rules:
- Identify 3 to 5 direct competitors from the content. If you cannot find
  clear URLs, make a best-effort guess (e.g. append /changelog to the homepage).
- changelog_url is required — guess /changelog or /blog if not explicit.
- Return ONLY the JSON array. Nothing else."""


def planner_node(state: dict) -> dict:
    """
    Stage 1 — LLM identifies competitors from pre-fetched context.
    Stores the task list in state["competitor_tasks"].
    The route_to_fetchers conditional edge then fans out Send objects.
    """
    category = state.get("category", "AI software")
    content_pieces = state.get("fetched_content", [])
    context = "\n\n---\n\n".join(content_pieces[:5])[:4000] or "No pre-fetched content."

    llm = GroqLLM().get_llm(temperature=0)
    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(
            content=(
                f"Product category: {category}\n\n"
                f"Pre-fetched content:\n{context}\n\n"
                "Return the JSON competitor array now."
            )
        ),
    ]

    response = llm.invoke(messages)
    raw = (
        response.content
        .strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )

    try:
        competitors_raw = json.loads(raw)
        if not isinstance(competitors_raw, list):
            competitors_raw = []
    except json.JSONDecodeError:
        competitors_raw = []

    # Build validated CompetitorTask dicts
    tasks = []
    for item in competitors_raw:
        task = CompetitorTask(
            name=item.get("name", "Unknown"),
            website_url=item.get("website_url", ""),
            changelog_url=item.get("changelog_url", ""),
            category=category,
        )
        tasks.append(task.model_dump())

    # Node must return a dict — Send objects are emitted by the edge function
    return {"competitor_tasks": tasks}


def route_to_fetchers(state: dict) -> list[Send]:
    """
    Conditional edge function — reads competitor_tasks from state and
    returns one Send per competitor to trigger parallel fetch branches.
    If no tasks found, routes directly to compiler for graceful termination.
    """
    tasks = state.get("competitor_tasks", [])
    if not tasks:
        return [Send("compiler", {})]
    return [Send("fetch_competitor", task) for task in tasks]


# ---------------------------------------------------------------------------
# Stage 2 — Per-competitor parallel fetch node
# ---------------------------------------------------------------------------

def competitor_fetch_node(task: dict) -> dict:
    """
    Receives one CompetitorTask dict. Calls all 3 Firecrawl tools concurrently
    with ThreadPoolExecutor(max_workers=3) and returns the merged result.

    Returns {"competitor_results": [combined_dict]} where the list is merged
    across all parallel branches by the operator.add reducer on CompetitorState.
    """
    name = task.get("name", "Unknown")
    website_url = task.get("website_url", "")
    changelog_url = task.get("changelog_url", "") or (
        website_url.rstrip("/") + "/changelog" if website_url else ""
    )

    results = {
        "name": name,
        "website_url": website_url,
        "changelog_url": changelog_url,
        "website_data": None,
        "changelog_data": None,
        "producthunt_data": None,
    }

    # Define the three fetch callables
    def _fetch_website():
        if not website_url:
            return ("website_data", json.dumps({"competitor": name, "error": "No URL", "confidence": 0.0}))
        raw = fetch_competitor_website.invoke({"competitor_name": name, "website_url": website_url})
        return ("website_data", raw)

    def _fetch_changelog():
        if not changelog_url:
            return ("changelog_data", json.dumps({"competitor": name, "error": "No changelog URL", "confidence": 0.0}))
        raw = fetch_competitor_changelog.invoke({"competitor_name": name, "changelog_url": changelog_url})
        return ("changelog_data", raw)

    def _fetch_producthunt():
        raw = fetch_producthunt_launches.invoke({"competitor_name": name})
        return ("producthunt_data", raw)

    # Run all three concurrently — one Firecrawl credit each
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(_fetch_website),
            executor.submit(_fetch_changelog),
            executor.submit(_fetch_producthunt),
        ]
        for future in as_completed(futures):
            try:
                key, value = future.result()
                results[key] = value
            except Exception as e:
                # Non-fatal — log and continue; compiler handles missing data gracefully
                print(f"[competitor_fetch_node] Tool error for {name}: {e}")

    # Deserialize JSON strings to dicts for the compiler
    for field in ("website_data", "changelog_data", "producthunt_data"):
        raw_val = results.get(field)
        if isinstance(raw_val, str):
            try:
                results[field] = json.loads(raw_val)
            except json.JSONDecodeError:
                results[field] = {"raw": raw_val}

    return {"competitor_results": [results]}


# ---------------------------------------------------------------------------
# Stage 3 — Compiler node
# ---------------------------------------------------------------------------

COMPILER_SYSTEM = """You are a data extraction assistant for competitive intelligence.

Based on the per-competitor research data below, produce a single structured
JSON object. Return ONLY valid JSON — no preamble, no markdown fences.

Schema:
{
  "competitors": [
    {
      "name": "string",
      "website": "string",
      "tagline": "string",
      "features": {
        "feature_name": {
          "present": true,
          "confidence": 0.85
        }
      },
      "last_updated": "ISO date string",
      "recent_launches": ["string"],
      "pricing_tier": "string",
      "sources": [
        {
          "url": "string",
          "title": "string",
          "retrieved_at": "ISO date string",
          "confidence": 0.85
        }
      ]
    }
  ],
  "feature_columns": ["ordered list of all feature names across competitors"],
  "category_summary": "2-sentence synthesis of the competitive landscape",
  "standard_features": ["features present in 3+ competitors"],
  "differentiator_features": ["features present in 1-2 competitors only"],
  "missing_features": ["important capabilities no competitor has yet"],
  "overall_confidence": 0.75
}

Rules:
- Include every competitor that returned at least one successful data fetch.
- Use consistent snake_case keys for all feature names across competitors.
- overall_confidence = average of all per-tool confidence scores received.
- missing_features = genuine market gaps, NOT data collection gaps."""


NARRATIVE_SYSTEM = """You are a senior Competitive Intelligence Analyst. You receive structured JSON data
about competitors and produce a comprehensive, actionable competitive intelligence report.

Your report MUST include:
1. **Executive Summary** — 3-4 sentences on who dominates and why.
2. **Competitor Profiles** — For each competitor: positioning, key features, pricing tier, recent launches.
3. **SWOT vs Our Product** — Specific strengths and weaknesses of competitors relative to us.
4. **Feature Gap Analysis** — What standard features everyone has, what differentiates players, and genuine market gaps.
5. **Positioning Map** — How competitors position themselves (premium/budget, enterprise/SMB, niche/broad).
6. **Strategic Recommendations** — 3 specific actions based on competitive gaps (NO new product feature suggestions).

Rules:
- Be specific — name features, pricing numbers, actual product names.
- Do NOT suggest building new product features — focus on positioning, messaging, and GTM strategy.
- Use markdown formatting with headers and tables where appropriate.
- Minimum 400 words."""


def compiler_node(state: dict) -> dict:
    """
    Final aggregation node. Runs after all parallel fetch branches complete.
    Reads state["competitor_results"] (list merged by operator.add reducer),
    calls the LLM for structured extraction AND a full narrative report.
    """
    competitor_results = state.get("competitor_results", [])

    if not competitor_results:
        empty_msg = "No competitor data was fetched — all tool calls failed or returned empty."
        empty = CompetitivePayload(
            competitors=[],
            feature_columns=[],
            category_summary=empty_msg,
            standard_features=[],
            differentiator_features=[],
            missing_features=[],
            overall_confidence=0.1,
        )
        return {
            "structured_output": empty.model_dump(),
            "analysis_result": empty_msg,
        }

    research_dump = json.dumps(competitor_results, indent=2)[:6000]
    llm = GroqLLM().get_llm(temperature=0)

    # ---- Step 1: Structured JSON extraction ----
    try:
        struct_messages = [
            SystemMessage(content=COMPILER_SYSTEM),
            HumanMessage(content=f"Per-competitor research data:\n{research_dump}"),
        ]
        struct_response = llm.invoke(struct_messages)
        content = (
            struct_response.content
            .strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        payload_dict = json.loads(content)
        payload = CompetitivePayload(**payload_dict)

    except Exception as e:
        payload = CompetitivePayload(
            competitors=[],
            feature_columns=[],
            category_summary=f"Structured extraction failed: {str(e)[:120]}",
            standard_features=[],
            differentiator_features=[],
            missing_features=[],
            overall_confidence=0.1,
        )

    # ---- Step 2: Full narrative report from structured data ----
    try:
        narrative_messages = [
            SystemMessage(content=NARRATIVE_SYSTEM),
            HumanMessage(
                content=(
                    f"Structured competitive intelligence data:\n"
                    f"{json.dumps(payload.model_dump(), indent=2)[:5000]}\n\n"
                    f"Write the full competitive intelligence report now."
                )
            ),
        ]
        narrative_response = llm.invoke(narrative_messages)
        analysis_result = narrative_response.content.strip()
    except Exception as e:
        analysis_result = (
            f"Narrative report generation failed: {e}\n\n"
            f"Structured summary: {payload.category_summary}"
        )

    return {
        "structured_output": payload.model_dump(),
        "analysis_result": analysis_result,
    }
