"""
LinkedIn Ad Library Utility — Public sponsored-content per advertiser.

Approach:
  1. Primary: Firecrawl (converts the LinkedIn Ad Library page to LLM-ready markdown).
  2. Fallback: Playwright headless browser when Firecrawl fails or returns no content.

LinkedIn Ad Library URL pattern:
  https://www.linkedin.com/ad-library/search?q={advertiser}&dateRange=pastMonth

Environment variable required (Firecrawl path):
  FIRECRAWL_API_KEY  — from https://www.firecrawl.dev/

No authentication is needed for public LinkedIn Ad Library pages.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

_LINKEDIN_AD_LIBRARY_BASE = "https://www.linkedin.com/ad-library/search"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def fetch_linkedin_ads(
    advertiser: str,
    date_range: str = "pastMonth",
    max_scroll_pages: int = 3,
    use_playwright_fallback: bool = True,
) -> dict:
    """Fetch LinkedIn sponsored-content for an advertiser.

    Tries Firecrawl first; falls back to Playwright if Firecrawl returns
    insufficient content (< 200 chars of markdown).

    Args:
        advertiser:             Company / brand name to search.
        date_range:             LinkedIn date-range param.  Common values:
                                  "pastDay", "pastWeek", "pastMonth" (default),
                                  "pastYear", "allTime".
        max_scroll_pages:       Playwright scroll iterations for dynamic content.
        use_playwright_fallback: Whether to attempt Playwright if Firecrawl fails.

    Returns:
        dict with keys:
          "advertiser"  — query used
          "source"      — "firecrawl" | "playwright" | "error"
          "content"     — markdown / text content
          "ads"         — list of parsed ad objects (best-effort)
          "error"       — error string or None
    """
    url = _build_url(advertiser, date_range)

    # --- Attempt 1: Firecrawl ---
    firecrawl_result = _firecrawl_fetch(url)
    if firecrawl_result["content"] and len(firecrawl_result["content"]) > 200:
        ads = _parse_ads_from_markdown(firecrawl_result["content"], advertiser)
        return {
            "advertiser": advertiser,
            "source": "firecrawl",
            "content": firecrawl_result["content"],
            "ads": ads,
            "error": None,
        }

    # --- Attempt 2: Playwright fallback ---
    if use_playwright_fallback:
        pw_result = _playwright_fetch(url, max_scroll_pages=max_scroll_pages)
        if pw_result["content"]:
            ads = _parse_ads_from_markdown(pw_result["content"], advertiser)
            return {
                "advertiser": advertiser,
                "source": "playwright",
                "content": pw_result["content"],
                "ads": ads,
                "error": pw_result.get("error"),
            }

    # Both failed
    combined_error = (
        firecrawl_result.get("error", "Firecrawl returned empty content")
        + " | Playwright unavailable or also failed."
    )
    return {
        "advertiser": advertiser,
        "source": "error",
        "content": "",
        "ads": [],
        "error": combined_error,
    }


# ---------------------------------------------------------------------------
# Private: build URL
# ---------------------------------------------------------------------------
def _build_url(advertiser: str, date_range: str) -> str:
    params = urllib.parse.urlencode({"q": advertiser, "dateRange": date_range})
    return f"{_LINKEDIN_AD_LIBRARY_BASE}?{params}"


# ---------------------------------------------------------------------------
# Private: Firecrawl fetch
# ---------------------------------------------------------------------------
def _firecrawl_fetch(url: str) -> dict:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return {"content": "", "error": "FIRECRAWL_API_KEY not set."}

    try:
        from firecrawl import FirecrawlApp  # type: ignore

        app = FirecrawlApp(api_key=api_key)
        # Use scrape with markdown + actions to wait for dynamic content
        scraped = app.scrape(
            url,
            formats=["markdown"],
            wait_for=3000,  # ms — wait for LinkedIn JS to render
        )
        # firecrawl-py v2 returns a ScrapeResponse object
        if hasattr(scraped, "markdown"):
            content = scraped.markdown or ""
        elif isinstance(scraped, dict):
            content = scraped.get("markdown", "")
        else:
            content = str(scraped)
        return {"content": content, "error": None}
    except Exception as exc:
        return {"content": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# Private: Playwright fetch
# ---------------------------------------------------------------------------
def _playwright_fetch(url: str, max_scroll_pages: int = 3) -> dict:
    try:
        from src.utils.playwright_utils import playwright_scrape  # type: ignore

        content = playwright_scrape(
            url=url,
            wait_for_selector=None,
            scroll_count=max_scroll_pages,
        )
        return {"content": content, "error": None}
    except ImportError:
        return {"content": "", "error": "playwright_utils not available."}
    except Exception as exc:
        return {"content": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# Private: best-effort ad parser from markdown
# ---------------------------------------------------------------------------
def _parse_ads_from_markdown(markdown: str, advertiser: str) -> list[dict]:
    """Extract individual ad entries from the LinkedIn Ad Library markdown.

    LinkedIn renders ad cards with headlines, body copy, and CTA buttons.
    This is a heuristic parser — quality depends on Firecrawl/Playwright output.

    Returns a list of dicts with keys: headline, body, cta, url.
    """
    ads = []

    # Split on horizontal rules or repeated newlines (card boundaries)
    blocks = re.split(r"\n{3,}|---+", markdown)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 30:
            continue

        # Skip navigation / boilerplate blocks
        if any(
            kw in block.lower()
            for kw in ("sign in", "privacy policy", "cookie", "terms of service")
        ):
            continue

        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        headline = lines[0].lstrip("#").strip()
        body = " ".join(lines[1:3]) if len(lines) > 1 else ""

        # Look for CTA-like phrases
        cta = ""
        for line in lines:
            if any(
                cw in line.lower()
                for cw in (
                    "learn more",
                    "sign up",
                    "get started",
                    "download",
                    "try free",
                    "request demo",
                    "book a demo",
                    "contact us",
                )
            ):
                cta = line.strip()
                break

        # Look for URLs
        url_match = re.search(r"https?://[^\s\)\"]+", block)
        url = url_match.group(0) if url_match else ""

        if headline and headline.lower() not in ("ad", "sponsored", advertiser.lower()):
            ads.append(
                {
                    "headline": headline,
                    "body": body,
                    "cta": cta,
                    "url": url,
                }
            )

    return ads[:30]  # Cap at 30 ads to keep context manageable
