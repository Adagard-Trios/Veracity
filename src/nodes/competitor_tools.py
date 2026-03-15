"""
Competitor Tools — Live Firecrawl-powered data fetchers.

These three tools replace the old LLM-on-pre-fetched-text tools entirely.
They are NOT used as LangChain @tool decorated functions in a ReAct loop —
instead they are called directly (as plain functions) inside competitor_fetch_node,
which invokes all three concurrently via ThreadPoolExecutor for maximum throughput.

Public interface (still @tool decorated for LangGraph compatibility):
    fetch_competitor_website(competitor_name, website_url) -> str (JSON)
    fetch_competitor_changelog(competitor_name, changelog_url) -> str (JSON)
    fetch_producthunt_launches(competitor_name) -> str (JSON)
"""

import os
import json
import httpx
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Firecrawl core
# ---------------------------------------------------------------------------

def _firecrawl_api_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set in environment.")
    return key


FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def _firecrawl_scrape(url: str, prompt: str | None = None) -> dict:
    """
    Core Firecrawl call — LLM-ready markdown + metadata.
    Uses structured extract mode when a prompt is provided.
    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    headers = {"Authorization": f"Bearer {_firecrawl_api_key()}"}

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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def fetch_competitor_website(competitor_name: str, website_url: str) -> str:
    """
    Fetches a competitor's homepage using Firecrawl structured extraction.
    Extracts tagline, feature list, pricing tier, and positioning language.
    Returns a JSON string. Call this first for each competitor.
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
    if a changelog or blog URL is known or can be inferred (/changelog, /blog).
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
