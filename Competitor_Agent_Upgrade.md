# Competitor Agent — Upgrade Plan

> Give this file to GitHub Copilot alongside `FRONTEND_BUILD_PLAN.md` and `copilot-instructions.md`.
> Work through the steps in the priority order listed at the bottom.

---

## Context

The existing competitor agent (`competitor_graph.py`, `competitor_node.py`, `competitor_state.py`) uses two LLM-only tools that operate on pre-fetched content passed in from the information fetcher. It produces a raw string `analysis_result`.

**What is wrong with the current state:**
- No live data fetching — `search_competitors` and `analyze_competitor_strengths` are LLM prompts on already-collected text, not real signal sources
- No Firecrawl, no ProductHunt, no changelog scraping
- Output is an unstructured string — the frontend `CompetitivePayload` TypeScript type is not satisfied
- No confidence scores on any finding
- No SSE `artifact_update` event emitted after completion

**What the target state must deliver:**
- Live fetching from competitor websites, changelogs, and Product Hunt via Firecrawl
- Structured `CompetitivePayload` output as a Pydantic model that maps 1:1 to the frontend type
- Confidence scores on every competitor record and the overall payload
- A source trail (`list[SourceItem]`) attached to every finding
- An `artifact_update` SSE event emitted once the compiler node finishes

---

## Files to Create / Modify

| File | Action | Priority |
|---|---|---|
| `competitor_schemas.py` | **Create new** | 1 — everything depends on this |
| `competitor_state.py` | **Modify** — add `structured_output` field | 2 |
| `competitor_tools.py` | **Create new** — replaces the two old tools | 3 |
| `competitor_node.py` | **Rewrite** — new agent node + compiler node | 4 |
| `competitor_graph.py` | **Modify** — wire compiler node, update edges | 5 |
| `veracity_graph.py` | **Modify** — add SSE emit after sub-graph completes | 6 |

---

## Step 1 — Create `competitor_schemas.py`

Create this file in the same directory as the other competitor agent files.

```python
# competitor_schemas.py
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class SourceItem(BaseModel):
    url: str
    title: str
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: float = Field(ge=0.0, le=1.0)


class FeatureEntry(BaseModel):
    """A single feature cell in the competitive matrix."""
    present: bool | str          # True/False or a short note like "partial", "beta"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    source: SourceItem | None = None


class CompetitorRecord(BaseModel):
    name: str
    website: str
    tagline: str = ""
    features: dict[str, FeatureEntry]
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    recent_launches: list[str] = Field(default_factory=list)
    pricing_tier: str = ""
    sources: list[SourceItem] = Field(default_factory=list)


class CompetitivePayload(BaseModel):
    """
    The exact payload emitted as artifact_update for domain=competitive_landscape.
    Maps 1:1 to the frontend CompetitivePayload TypeScript type in src/types/artifacts.ts.
    """
    competitors: list[CompetitorRecord]
    feature_columns: list[str]
    category_summary: str
    standard_features: list[str]
    differentiator_features: list[str]
    missing_features: list[str]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceItem] = Field(default_factory=list)


class AgentEventPayload(BaseModel):
    """Wrapper matching the AgentEvent SSE contract consumed by the frontend."""
    type: Literal["artifact_update"] = "artifact_update"
    domain: Literal["competitive_landscape"] = "competitive_landscape"
    payload: CompetitivePayload
```

---

## Step 2 — Modify `competitor_state.py`

Add `structured_output` field. Keep `analysis_result` exactly as-is for backward compatibility with the main compiler in `veracity_graph.py`.

```python
# competitor_state.py
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import add_messages


class CompetitorState(TypedDict):
    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    analysis_result: str               # kept — main compiler reads this
    structured_output: dict[str, Any]  # new — CompetitivePayload as dict for SSE emit
```

---

## Step 3 — Create `competitor_tools.py`

Create this new file. It replaces `search_competitors` and `analyze_competitor_strengths` entirely. Do not keep the old tools.

```python
# competitor_tools.py
import os
import json
import httpx
from langchain_core.tools import tool


FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]
FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def _firecrawl_scrape(url: str, prompt: str | None = None) -> dict:
    """
    Core Firecrawl call. Returns LLM-ready markdown + metadata.
    Uses structured extract mode when a prompt is provided.
    Raises httpx.HTTPStatusError on non-2xx responses — callers must handle.
    """
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}"}

    if prompt:
        body = {
            "url": url,
            "formats": ["extract"],
            "extract": {"prompt": prompt},
        }
    else:
        body = {"url": url, "formats": ["markdown"]}

    resp = httpx.post(
        f"{FIRECRAWL_BASE}/scrape",
        json=body,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@tool
def fetch_competitor_website(competitor_name: str, website_url: str) -> str:
    """
    Fetches a competitor's homepage using Firecrawl structured extraction.
    Extracts tagline, feature list, pricing tier, and positioning language.
    Returns a JSON string. Always call this first for each competitor.
    """
    extract_prompt = """
    Extract from this page:
    - company_tagline: their main value proposition in one sentence
    - features: list of product features or capabilities mentioned
    - pricing_tier: pricing model if visible (e.g. "freemium", "$49/mo starter",
      "enterprise only", "not shown")
    - target_customer: who they seem to be selling to (one sentence)
    - positioning_keywords: 5-10 words that define their market positioning
    Return as JSON only. No preamble, no markdown fences.
    """
    try:
        result = _firecrawl_scrape(website_url, prompt=extract_prompt)
        extracted = result.get("data", {}).get("extract", {})
        return json.dumps({
            "competitor": competitor_name,
            "url": website_url,
            "data": extracted,
            "confidence": 0.85 if extracted else 0.3,
        })
    except Exception as e:
        return json.dumps({
            "competitor": competitor_name,
            "url": website_url,
            "error": str(e),
            "confidence": 0.0,
        })


@tool
def fetch_competitor_changelog(competitor_name: str, changelog_url: str) -> str:
    """
    Scrapes a competitor's changelog, release notes page, or engineering blog
    for recent product launches. Call this after fetch_competitor_website
    if a changelog or blog URL is known or can be inferred (e.g. /changelog, /blog).
    Returns a JSON string with the 5 most recent launch items.
    """
    extract_prompt = """
    Extract the 5 most recent product updates, feature launches, or release notes.
    For each item return:
    - date: when it was released (ISO format if possible, otherwise as shown)
    - title: short name of the feature or change
    - description: one sentence summary of what changed
    Return as a JSON array only. No preamble, no markdown fences.
    If the page has no changelog content, return an empty array [].
    """
    try:
        result = _firecrawl_scrape(changelog_url, prompt=extract_prompt)
        items = result.get("data", {}).get("extract", [])
        return json.dumps({
            "competitor": competitor_name,
            "changelog_url": changelog_url,
            "recent_launches": items if isinstance(items, list) else [],
            "confidence": 0.8 if items else 0.4,
        })
    except Exception as e:
        return json.dumps({
            "competitor": competitor_name,
            "changelog_url": changelog_url,
            "error": str(e),
            "confidence": 0.0,
        })


@tool
def fetch_producthunt_launches(competitor_name: str) -> str:
    """
    Searches Product Hunt for a competitor's launches and community reception.
    Provides social proof signal: upvotes, launch dates, community themes.
    Call this for each competitor after fetching their website.
    Returns a JSON string.
    """
    search_url = (
        f"https://www.producthunt.com/search?q={competitor_name.replace(' ', '+')}"
    )
    extract_prompt = f"""
    Find Product Hunt listings for the company or product named "{competitor_name}".
    For each listing return:
    - product_name: name as shown on Product Hunt
    - tagline: their Product Hunt tagline
    - upvotes: number of upvotes if visible (integer or null)
    - launch_date: when they launched on Product Hunt
    - top_comment_themes: 2-3 recurring themes from community comments if visible
    Return as a JSON array only. No preamble, no markdown fences.
    If no relevant listings are found, return an empty array [].
    """
    try:
        result = _firecrawl_scrape(search_url, prompt=extract_prompt)
        launches = result.get("data", {}).get("extract", [])
        return json.dumps({
            "competitor": competitor_name,
            "producthunt_url": search_url,
            "launches": launches if isinstance(launches, list) else [],
            "confidence": 0.75 if launches else 0.3,
        })
    except Exception as e:
        return json.dumps({
            "competitor": competitor_name,
            "producthunt_url": search_url,
            "error": str(e),
            "confidence": 0.0,
        })


@tool
def extract_feature_matrix(
    category: str,
    competitors_json: str,
    fetched_content: str,
) -> str:
    """
    Synthesis tool — call this LAST, after all individual competitor fetches are done.
    Signals to the agent that data gathering is complete so the compiler node
    can produce the final structured output.

    competitors_json: JSON array string of competitor names already researched
    fetched_content: concatenated results from all previous tool calls
    category: the product category being analysed

    Returns a JSON summary object. The compiler node uses this plus the full
    message history to build the final CompetitivePayload.
    """
    try:
        competitors = json.loads(competitors_json)
    except json.JSONDecodeError:
        competitors = []

    return json.dumps({
        "task": "feature_matrix_extraction",
        "status": "ready_for_compiler",
        "category": category,
        "competitors_researched": competitors,
        "content_length": len(fetched_content),
    })
```

---

## Step 4 — Rewrite `competitor_node.py`

Replace the entire file. Two functions: the ReAct agent node (same interface, new tools and prompt) and a new `compiler_node` that produces the typed `CompetitivePayload`.

```python
# competitor_node.py
import json
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from competitor_tools import (
    fetch_competitor_website,
    fetch_competitor_changelog,
    fetch_producthunt_launches,
    extract_feature_matrix,
)
from competitor_schemas import CompetitivePayload


# --- LLM and tool binding ---
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

tools = [
    fetch_competitor_website,
    fetch_competitor_changelog,
    fetch_producthunt_launches,
    extract_feature_matrix,
]

llm_with_tools = llm.bind_tools(tools)


SYSTEM_PROMPT = """You are a Competitive Intelligence Agent. Your job is to build a live,
structured competitive landscape for a given product category.

You have four tools that fetch LIVE data. You must use them — do not rely on training knowledge.

Your process (follow this order strictly):
1. Read the pre-fetched context to identify 3-5 key competitors and their website URLs.
2. For each competitor: call fetch_competitor_website with their URL.
3. For each competitor: call fetch_competitor_changelog if a changelog or blog URL
   exists (try appending /changelog, /releases, or /blog if not explicitly stated).
4. For each competitor: call fetch_producthunt_launches to get community signal.
5. Once ALL competitors are covered: call extract_feature_matrix to signal completion.

Rules:
- Cover all competitors before calling extract_feature_matrix.
- Every claim must trace to a tool call result — never your prior knowledge.
- If a tool call fails for one competitor, continue with the others.
- Be systematic — one competitor at a time, all three tools per competitor."""


def competitor_agent_node(state: dict) -> dict:
    """
    ReAct agent node — runs the live data gathering loop.
    Injects system prompt and context on first invocation.
    """
    messages = state["messages"]

    if not messages or not isinstance(messages[0], SystemMessage):
        system_msg = SystemMessage(content=SYSTEM_PROMPT)
        context_msg = HumanMessage(
            content=(
                f"Category: {state.get('category', 'AI SDR / digital workers')}\n\n"
                "Pre-fetched context — use this to identify competitor names and URLs, "
                "then fetch LIVE data for each using your tools:\n\n"
                f"{state.get('fetched_content', ['No pre-fetched content'])[0][:3000]}\n\n"
                "Begin your competitive analysis now. Start with the first competitor."
            )
        )
        messages = [system_msg, context_msg] + list(messages)

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def compiler_node(state: dict) -> dict:
    """
    Final compiler node — runs AFTER the ReAct loop exits (no more tool calls).
    Collects all tool results from the message history and produces a typed
    CompetitivePayload via a structured extraction LLM call.

    Writes to:
      state["structured_output"] — CompetitivePayload as dict (for SSE emit)
      state["analysis_result"]   — plain string summary (backward compat)
    """
    # Collect all tool call results from message history
    tool_results = []
    for msg in state["messages"]:
        if hasattr(msg, "type") and msg.type == "tool":
            try:
                tool_results.append(json.loads(msg.content))
            except (json.JSONDecodeError, AttributeError):
                tool_results.append({"raw": getattr(msg, "content", str(msg))})

    if not tool_results:
        empty_payload = CompetitivePayload(
            competitors=[],
            feature_columns=[],
            category_summary="No live data was fetched. Tool calls did not execute.",
            standard_features=[],
            differentiator_features=[],
            missing_features=[],
            overall_confidence=0.1,
        )
        return {
            "structured_output": empty_payload.model_dump(),
            "analysis_result": empty_payload.category_summary,
        }

    extraction_prompt = f"""You are a data extraction assistant. Based on the tool results
from live competitive research below, produce a structured JSON object.

Return ONLY valid JSON matching this exact schema — no preamble, no markdown fences:

{{
  "competitors": [
    {{
      "name": "string",
      "website": "string",
      "tagline": "string",
      "features": {{
        "feature_name": {{
          "present": true,
          "confidence": 0.85
        }}
      }},
      "last_updated": "ISO date string",
      "recent_launches": ["string"],
      "pricing_tier": "string",
      "sources": [
        {{
          "url": "string",
          "title": "string",
          "retrieved_at": "ISO date string",
          "confidence": 0.85
        }}
      ]
    }}
  ],
  "feature_columns": ["ordered list of all feature names found across competitors"],
  "category_summary": "2-sentence synthesis of the competitive landscape",
  "standard_features": ["features present in 3 or more competitors"],
  "differentiator_features": ["features present in only 1-2 competitors"],
  "missing_features": ["important capabilities no competitor has yet"],
  "overall_confidence": 0.75
}}

Rules:
- Include every competitor that returned at least one successful tool result.
- Use consistent snake_case names for all feature keys across all competitors.
- overall_confidence should reflect average data quality across tool calls.
- missing_features should be genuine market gaps, not data collection gaps.

Tool results from live research:
{json.dumps(tool_results, indent=2)[:6000]}"""

    extraction_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

    try:
        raw = extraction_llm.invoke([HumanMessage(content=extraction_prompt)])
        content = (
            raw.content
            .strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        payload_dict = json.loads(content)
        payload = CompetitivePayload(**payload_dict)

    except Exception as e:
        # Graceful degradation — partial payload beats a crash
        payload = CompetitivePayload(
            competitors=[],
            feature_columns=[],
            category_summary=f"Structured extraction failed: {str(e)[:120]}",
            standard_features=[],
            differentiator_features=[],
            missing_features=[],
            overall_confidence=0.1,
        )

    return {
        "structured_output": payload.model_dump(),
        "analysis_result": payload.category_summary,
    }
```

---

## Step 5 — Modify `competitor_graph.py`

Three changes: update imports, replace the tool list, add the compiler node and reroute the exit edge.

**Update imports at the top of the file:**

```python
# Replace old imports with these
from competitor_node import competitor_agent_node, compiler_node
from competitor_tools import (
    fetch_competitor_website,
    fetch_competitor_changelog,
    fetch_producthunt_launches,
    extract_feature_matrix,
)
```

**Replace the tool list** (remove `search_competitors` and `analyze_competitor_strengths`):

```python
tools = [
    fetch_competitor_website,
    fetch_competitor_changelog,
    fetch_producthunt_launches,
    extract_feature_matrix,
]
```

**Replace the graph assembly function entirely:**

```python
def build_competitor_graph():
    graph = StateGraph(CompetitorState)

    graph.add_node("agent", competitor_agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("compiler", compiler_node)       # new node

    graph.set_entry_point("agent")

    # ReAct loop exits to compiler node instead of END
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: "compiler",    # was END — now routes to compiler
        }
    )

    graph.add_edge("tools", "agent")
    graph.add_edge("compiler", END)     # compiler is the new terminal node

    return graph.compile()


competitor_graph = build_competitor_graph()
```

---

## Step 6 — Modify `veracity_graph.py`

Add an SSE emit helper and call it after the competitor sub-graph result is collected.

**Add this helper near the top of the file (before the graph definition):**

```python
# veracity_graph.py — add this helper function

import json

DOMAIN_AGENT_ID_MAP = {
    "competitive_landscape": 3,
    "market_trends": 2,
    "win_loss": 4,
    "pricing_packaging": 5,
    "positioning": 6,
    "adjacent_markets": 7,
}


def emit_sse_artifact(domain: str, payload: dict, confidence: float, sse_queue) -> None:
    """
    Pushes two SSE events to the queue consumed by the /api/stream endpoint:
      1. artifact_update — structured payload for the frontend dashboard card
      2. agent_complete  — signals the agent status pill to show green + confidence

    sse_queue must be a thread-safe queue.Queue or equivalent.
    Pass None during unit tests — this function becomes a no-op.
    """
    if sse_queue is None:
        return

    artifact_event = {
        "type": "artifact_update",
        "domain": domain,
        "payload": payload,
    }
    sse_queue.put(f"data: {json.dumps(artifact_event)}\n\n")

    complete_event = {
        "type": "agent_complete",
        "agentId": DOMAIN_AGENT_ID_MAP.get(domain, 3),
        "confidence": round(confidence, 3),
    }
    sse_queue.put(f"data: {json.dumps(complete_event)}\n\n")
```

**In the parallel join / `compiler_and_storage` node**, find where competitor output is collected and add the emit call:

```python
# Inside the parallel join node that runs after all 6 sub-graphs complete:

competitor_output = state.get("competitor_output", {})
structured = competitor_output.get("structured_output", {})
confidence = structured.get("overall_confidence", 0.5)

if structured:
    emit_sse_artifact(
        domain="competitive_landscape",
        payload=structured,
        confidence=confidence,
        sse_queue=state.get("sse_queue"),
    )
```

> **Note:** If SSE is handled differently in your implementation (FastAPI `StreamingResponse`, async queue, Redis pub/sub), adapt the internals of `emit_sse_artifact` to match. The event JSON structure (`type`, `domain`, `payload`, `agentId`, `confidence`) must stay exactly as shown — the frontend validates this shape with Zod and will silently discard non-conforming events.

---

## Environment Variables Required

Add to backend `.env` only. Never expose to the frontend.

```bash
FIRECRAWL_API_KEY=your_firecrawl_key_here
```

**Firecrawl credit budget for the hackathon:**
- Free tier: 500 credits
- Each `_firecrawl_scrape` call = 1 credit
- Full pipeline run (4 competitors × 3 tool calls each) = ~12 credits
- Available test runs before exhausting free tier: ~40

Test tools individually during development to conserve credits. Do not run the full pipeline repeatedly while debugging.

---

## Dependency to Add

```bash
pip install httpx
```

Add to `requirements.txt`:

```
httpx>=0.27.0
```

---

## What the Frontend Receives

After all steps are complete, the frontend `CompetitiveLandscapeCard` receives this SSE event shape:

```json
{
  "type": "artifact_update",
  "domain": "competitive_landscape",
  "payload": {
    "competitors": [
      {
        "name": "Lilian",
        "website": "https://lilian.ai",
        "tagline": "AI SDR that books meetings on autopilot",
        "features": {
          "email_personalization": { "present": true, "confidence": 0.9 },
          "linkedin_outreach": { "present": true, "confidence": 0.85 },
          "crm_integration": { "present": "partial", "confidence": 0.7 },
          "voice_calls": { "present": false, "confidence": 0.8 }
        },
        "last_updated": "2026-03-15T09:00:00",
        "recent_launches": [
          "Multi-inbox sending (Feb 2026)",
          "GPT-4o upgrade for personalization (Jan 2026)"
        ],
        "pricing_tier": "$500/mo starter",
        "sources": [
          {
            "url": "https://lilian.ai",
            "title": "Lilian homepage",
            "retrieved_at": "2026-03-15T09:00:00",
            "confidence": 0.9
          }
        ]
      }
    ],
    "feature_columns": [
      "email_personalization",
      "linkedin_outreach",
      "crm_integration",
      "voice_calls"
    ],
    "category_summary": "The AI SDR market is consolidating around email personalization as table stakes, with differentiation shifting to multi-channel orchestration and CRM depth.",
    "standard_features": ["email_personalization", "sequence_builder"],
    "differentiator_features": ["voice_calls", "linkedin_outreach"],
    "missing_features": ["inbound_qualification", "real_time_intent_signals"],
    "overall_confidence": 0.82,
    "sources": []
  }
}
```

---

## Hackathon Priority Order

Do these in strict order. Stop when time runs out — each step is independently valuable.

| # | Step | Est. time | Value if you stop here |
|---|---|---|---|
| 1 | Create `competitor_schemas.py` | 15 min | Defines the contract; all other steps depend on it |
| 2 | Modify `competitor_state.py` | 5 min | Unlocks `structured_output` field in graph state |
| 3 | Create `competitor_tools.py` — `fetch_competitor_website` first | 20 min | One live Firecrawl fetch beats zero |
| 4 | Rewrite `competitor_node.py` — `compiler_node` function | 25 min | Typed JSON payload; frontend card renders correctly |
| 5 | Modify `competitor_graph.py` | 10 min | Compiler node wired into the graph |
| 6 | Add changelog + ProductHunt tools to `competitor_tools.py` | 20 min | Adds launch signal and community voice |
| 7 | Modify `veracity_graph.py` — SSE emit | 15 min | Frontend card updates in real-time during the demo |

**Minimum viable for demo:** Steps 1–5 (~75 min). The frontend renders a fully structured competitive card with confidence scores and source trail. Steps 6–7 add live richness and the real-time card animation that impresses judges.

---

## Team Coordination Notes

- **Frontend contract:** `CompetitivePayload` in `competitor_schemas.py` must stay in sync with `src/types/artifacts.ts` on the frontend. If any field is added or renamed, tell the frontend developer immediately.
- **SSE queue mechanism:** Confirm with whoever owns `veracity_graph.py` what the SSE queue implementation is (thread queue, async generator, Redis pub/sub) before starting Step 6. The `emit_sse_artifact` helper must use the same mechanism.
- **Groq rate limits:** `llama-3.3-70b-versatile` on the free tier has token-per-minute limits. If the compiler node hits limits during the demo, switch its model to `llama3-8b-8192` which has higher throughput at the cost of some output quality.
- **Firecrawl credits:** Test individual tools in isolation before running the full pipeline. Use `_firecrawl_scrape` directly in a scratch script to verify extraction prompts before wiring into the agent.