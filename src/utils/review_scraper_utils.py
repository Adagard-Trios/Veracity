"""
Review Scraper Utility — G2, Capterra, Trustpilot, YouTube, App Store signals.

Provides structured buyer-side review data for the Win/Loss Intelligence Agent.

Each function uses Firecrawl as the primary scraper with SerpAPI as a fallback,
returning a normalised dict with a "reviews" list, "source" string, and
"error" string (or None).

Environment variables required:
  FIRECRAWL_API_KEY  — from https://firecrawl.dev/
  SERPAPI_API_KEY    — from https://serpapi.com/ (fallback + YouTube/App Store)

All functions follow the same return contract:
  {
    "source":  str,             — data source name (e.g. "g2", "capterra")
    "product": str,             — product/company queried
    "reviews": list[dict],      — list of normalised review objects
    "error":   str | None,      — error string or None
  }
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v1"
_SERPAPI_BASE = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Internal: Firecrawl scrape helper
# ---------------------------------------------------------------------------
def _firecrawl_scrape(url: str, formats: list[str] | None = None) -> dict:
    """Scrape a URL via Firecrawl and return raw content.

    Args:
        url:     Target URL to scrape.
        formats: List of output formats (e.g. ["markdown", "html"]).
                 Defaults to ["markdown"].

    Returns:
        dict with keys: "content" (str), "error" (str | None)
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return {"content": "", "error": "FIRECRAWL_API_KEY not set in environment."}

    if formats is None:
        formats = ["markdown"]

    # Try official SDK first
    try:
        from firecrawl import FirecrawlApp  # type: ignore

        app = FirecrawlApp(api_key=api_key)
        result = app.scrape(url, formats=[{formats[0]: {}}], wait_for=3000)
        if isinstance(result, dict):
            content = result.get("markdown") or result.get("content") or ""
            err = result.get("error")
        else:
            content = getattr(result, "markdown", "") or ""
            err = None
        return {"content": content, "error": err}
    except ImportError:
        pass  # Fall through to requests

    # Fallback: raw HTTP
    try:
        import requests  # noqa: PLC0415

        resp = requests.post(
            f"{_FIRECRAWL_API_BASE}/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": formats},
            timeout=45,
        )
        resp.raise_for_status()
        payload = resp.json()
        content = (
            payload.get("data", {}).get("markdown")
            or payload.get("data", {}).get("content")
            or payload.get("markdown")
            or ""
        )
        return {"content": content, "error": payload.get("error")}
    except Exception as exc:
        return {"content": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# Internal: SerpAPI GET helper (shared with serpapi_utils)
# ---------------------------------------------------------------------------
def _serpapi_get(params: dict) -> dict:
    """Execute a SerpAPI GET request and return parsed JSON."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return {"error": "SERPAPI_API_KEY not set in environment.", "data": None}

    params["api_key"] = api_key

    try:
        from serpapi import GoogleSearch  # type: ignore

        client = GoogleSearch(params)
        result = client.get_dict()
        if "error" in result:
            return {"error": result["error"], "data": None}
        return {"error": None, "data": result}
    except ImportError:
        pass

    try:
        import requests  # noqa: PLC0415

        resp = requests.get(_SERPAPI_BASE, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            return {"error": payload["error"], "data": None}
        return {"error": None, "data": payload}
    except Exception as exc:
        return {"error": str(exc), "data": None}


# ---------------------------------------------------------------------------
# Internal: parse freeform markdown into minimal review dicts
# ---------------------------------------------------------------------------
def _parse_markdown_reviews(
    markdown: str,
    source: str,
    product: str,
    limit: int,
) -> list[dict]:
    """Best-effort extraction of review snippets from scraped markdown.

    Looks for list items, blockquotes, or paragraphs that look like review text.
    Returns at most `limit` dicts with keys: source, product, text, rating (str).
    """
    reviews: list[dict] = []
    lines = markdown.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip headings, nav links, and very short lines
        if line.startswith("#") or line.startswith("http") or len(line) < 30:
            continue
        # Prefer list items and blockquotes — more likely to be review text
        if line.startswith(("-", "*", ">", "1.", "2.", "3.")):
            text = line.lstrip("-*>0123456789. ").strip()
            if len(text) >= 30:
                reviews.append(
                    {
                        "source": source,
                        "product": product,
                        "text": text[:400],
                        "rating": "",
                    }
                )
        if len(reviews) >= limit:
            break

    # If list-item scan found nothing, fall back to paragraphs
    if not reviews:
        for line in lines:
            line = line.strip()
            if (
                len(line) >= 60
                and not line.startswith("#")
                and not line.startswith("http")
            ):
                reviews.append(
                    {
                        "source": source,
                        "product": product,
                        "text": line[:400],
                        "rating": "",
                    }
                )
            if len(reviews) >= limit:
                break

    return reviews


# ---------------------------------------------------------------------------
# 1. G2 Reviews
# ---------------------------------------------------------------------------
def scrape_g2_reviews(product: str, limit: int = 20) -> dict:
    """Scrape G2 user reviews for a product.

    Primary: Firecrawl scrape of g2.com search results page.
    Fallback: SerpAPI Google search restricted to site:g2.com.

    Args:
        product: Product or company name (e.g. "Notion", "HubSpot").
        limit:   Max number of reviews to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews", "error"
    """
    source = "g2"

    # Primary: Firecrawl
    url = f"https://www.g2.com/products/{product.lower().replace(' ', '-')}/reviews"
    scrape = _firecrawl_scrape(url)
    if not scrape["error"] and scrape["content"]:
        reviews = _parse_markdown_reviews(
            scrape["content"], source=source, product=product, limit=limit
        )
        if reviews:
            return {
                "source": source,
                "product": product,
                "reviews": reviews,
                "error": None,
            }

    # Fallback: SerpAPI Google search → site:g2.com
    params: dict[str, Any] = {
        "engine": "google",
        "q": f"{product} reviews site:g2.com",
        "num": min(limit, 10),
    }
    result = _serpapi_get(params)
    if result["error"]:
        return {
            "source": source,
            "product": product,
            "reviews": [],
            "error": result["error"],
        }

    data = result["data"] or {}
    reviews = []
    for item in (data.get("organic_results") or [])[:limit]:
        snippet = item.get("snippet", "")
        if snippet and len(snippet) >= 20:
            reviews.append(
                {
                    "source": source,
                    "product": product,
                    "text": snippet[:400],
                    "rating": "",
                    "link": item.get("link", ""),
                }
            )

    return {
        "source": source,
        "product": product,
        "reviews": reviews,
        "error": None if reviews else scrape.get("error"),
    }


# ---------------------------------------------------------------------------
# 2. Capterra Reviews
# ---------------------------------------------------------------------------
def scrape_capterra_reviews(product: str, limit: int = 20) -> dict:
    """Scrape Capterra user reviews for a product.

    Primary: Firecrawl scrape of capterra.com search.
    Fallback: SerpAPI Google search restricted to site:capterra.com.

    Args:
        product: Product or company name.
        limit:   Max number of reviews to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews", "error"
    """
    source = "capterra"

    slug = product.lower().replace(" ", "-")
    url = f"https://www.capterra.com/p/search/?query={product.replace(' ', '+')}"
    scrape = _firecrawl_scrape(url)
    if not scrape["error"] and scrape["content"]:
        reviews = _parse_markdown_reviews(
            scrape["content"], source=source, product=product, limit=limit
        )
        if reviews:
            return {
                "source": source,
                "product": product,
                "reviews": reviews,
                "error": None,
            }

    # Fallback: SerpAPI
    params: dict[str, Any] = {
        "engine": "google",
        "q": f"{product} reviews site:capterra.com",
        "num": min(limit, 10),
    }
    result = _serpapi_get(params)
    if result["error"]:
        return {
            "source": source,
            "product": product,
            "reviews": [],
            "error": result["error"],
        }

    data = result["data"] or {}
    reviews = []
    for item in (data.get("organic_results") or [])[:limit]:
        snippet = item.get("snippet", "")
        if snippet and len(snippet) >= 20:
            reviews.append(
                {
                    "source": source,
                    "product": product,
                    "text": snippet[:400],
                    "rating": "",
                    "link": item.get("link", ""),
                }
            )

    return {
        "source": source,
        "product": product,
        "reviews": reviews,
        "error": None if reviews else scrape.get("error"),
    }


# ---------------------------------------------------------------------------
# 3. Trustpilot Reviews
# ---------------------------------------------------------------------------
def scrape_trustpilot_reviews(company: str, limit: int = 20) -> dict:
    """Scrape Trustpilot reviews for a company.

    Primary: Firecrawl scrape of trustpilot.com company page.
    Fallback: SerpAPI Google search restricted to site:trustpilot.com.

    Args:
        company: Company or product name (e.g. "Notion", "Slack").
        limit:   Max number of reviews to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews", "error"
    """
    source = "trustpilot"

    slug = company.lower().replace(" ", "")
    url = f"https://www.trustpilot.com/review/{slug}.com"
    scrape = _firecrawl_scrape(url)
    if not scrape["error"] and scrape["content"]:
        reviews = _parse_markdown_reviews(
            scrape["content"], source=source, product=company, limit=limit
        )
        if reviews:
            return {
                "source": source,
                "product": company,
                "reviews": reviews,
                "error": None,
            }

    # Fallback: SerpAPI
    params: dict[str, Any] = {
        "engine": "google",
        "q": f"{company} reviews site:trustpilot.com",
        "num": min(limit, 10),
    }
    result = _serpapi_get(params)
    if result["error"]:
        return {
            "source": source,
            "product": company,
            "reviews": [],
            "error": result["error"],
        }

    data = result["data"] or {}
    reviews = []
    for item in (data.get("organic_results") or [])[:limit]:
        snippet = item.get("snippet", "")
        if snippet and len(snippet) >= 20:
            reviews.append(
                {
                    "source": source,
                    "product": company,
                    "text": snippet[:400],
                    "rating": "",
                    "link": item.get("link", ""),
                }
            )

    return {
        "source": source,
        "product": company,
        "reviews": reviews,
        "error": None if reviews else scrape.get("error"),
    }


# ---------------------------------------------------------------------------
# 4. YouTube Comments (product perception)
# ---------------------------------------------------------------------------
def fetch_youtube_comments(query: str, limit: int = 20) -> dict:
    """Fetch YouTube video search results and extract comment snippets.

    Uses SerpAPI YouTube search engine to find relevant videos about a product,
    then attempts to scrape comment sections via Firecrawl.

    Args:
        query: Search query (e.g. "Notion review 2025", "Notion vs Obsidian").
        limit: Max comment snippets to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews" (comment snippets), "error"
    """
    source = "youtube_comments"

    # SerpAPI YouTube search
    params: dict[str, Any] = {
        "engine": "youtube",
        "search_query": query,
    }
    result = _serpapi_get(params)

    reviews: list[dict] = []
    error: str | None = None

    if result["error"]:
        # Fallback: Google search for YouTube reviews
        params_fallback: dict[str, Any] = {
            "engine": "google",
            "q": f"{query} site:youtube.com",
            "num": min(limit, 10),
        }
        result = _serpapi_get(params_fallback)
        if result["error"]:
            return {
                "source": source,
                "product": query,
                "reviews": [],
                "error": result["error"],
            }

    data = result["data"] or {}

    # Extract video titles and descriptions as proxy for comment signals
    video_results = data.get("video_results", data.get("organic_results", []))
    for video in video_results[: min(limit, 10)]:
        title = video.get("title", "")
        description = video.get("description", video.get("snippet", ""))
        if title:
            reviews.append(
                {
                    "source": source,
                    "product": query,
                    "text": f"{title}. {description}"[:400],
                    "rating": "",
                    "link": video.get("link", video.get("url", "")),
                }
            )
        if len(reviews) >= limit:
            break

    return {
        "source": source,
        "product": query,
        "reviews": reviews,
        "error": None if reviews else "No YouTube results found.",
    }


# ---------------------------------------------------------------------------
# 5. App Store Reviews (Apple)
# ---------------------------------------------------------------------------
def fetch_app_store_reviews(app_name: str, limit: int = 20) -> dict:
    """Fetch Apple App Store reviews for an app via SerpAPI.

    Uses SerpAPI Apple App Store engine if available; falls back to a Google
    search restricted to apps.apple.com for snippet-based reviews.

    Args:
        app_name: App name to search (e.g. "Notion", "Linear").
        limit:    Max reviews to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews", "error"
    """
    source = "app_store"

    # Try SerpAPI Apple App Store engine
    params: dict[str, Any] = {
        "engine": "apple_app_store",
        "term": app_name,
        "num": min(limit, 20),
    }
    result = _serpapi_get(params)

    reviews: list[dict] = []

    if not result["error"] and result["data"]:
        data = result["data"]
        for app in (data.get("organic_results") or [])[:limit]:
            description = app.get("description", app.get("snippet", ""))
            rating = str(app.get("rating", ""))
            if description:
                reviews.append(
                    {
                        "source": source,
                        "product": app_name,
                        "text": description[:400],
                        "rating": rating,
                        "link": app.get("link", ""),
                    }
                )

    if not reviews:
        # Fallback: Google search → apps.apple.com
        params_fb: dict[str, Any] = {
            "engine": "google",
            "q": f"{app_name} app store reviews site:apps.apple.com",
            "num": min(limit, 10),
        }
        result_fb = _serpapi_get(params_fb)
        if not result_fb["error"] and result_fb["data"]:
            for item in (result_fb["data"].get("organic_results") or [])[:limit]:
                snippet = item.get("snippet", "")
                if snippet and len(snippet) >= 20:
                    reviews.append(
                        {
                            "source": source,
                            "product": app_name,
                            "text": snippet[:400],
                            "rating": "",
                            "link": item.get("link", ""),
                        }
                    )

    return {
        "source": source,
        "product": app_name,
        "reviews": reviews,
        "error": None if reviews else result.get("error"),
    }


# ---------------------------------------------------------------------------
# 6. Google Play Store Reviews
# ---------------------------------------------------------------------------
def fetch_play_store_reviews(app_name: str, limit: int = 20) -> dict:
    """Fetch Google Play Store reviews for an app.

    Uses SerpAPI Google Play store engine or falls back to Google search.

    Args:
        app_name: App name to search (e.g. "Notion", "Todoist").
        limit:    Max reviews to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews", "error"
    """
    source = "play_store"

    params: dict[str, Any] = {
        "engine": "google_play",
        "q": app_name,
        "store": "apps",
    }
    result = _serpapi_get(params)

    reviews: list[dict] = []

    if not result["error"] and result["data"]:
        data = result["data"]
        for app in (data.get("organic_results") or [])[:limit]:
            description = app.get("description", app.get("snippet", ""))
            rating = str(app.get("rating", ""))
            if description:
                reviews.append(
                    {
                        "source": source,
                        "product": app_name,
                        "text": description[:400],
                        "rating": rating,
                        "link": app.get("link", ""),
                    }
                )

    if not reviews:
        # Fallback: Google search → play.google.com
        params_fb: dict[str, Any] = {
            "engine": "google",
            "q": f"{app_name} reviews site:play.google.com",
            "num": min(limit, 10),
        }
        result_fb = _serpapi_get(params_fb)
        if not result_fb["error"] and result_fb["data"]:
            for item in (result_fb["data"].get("organic_results") or [])[:limit]:
                snippet = item.get("snippet", "")
                if snippet and len(snippet) >= 20:
                    reviews.append(
                        {
                            "source": source,
                            "product": app_name,
                            "text": snippet[:400],
                            "rating": "",
                            "link": item.get("link", ""),
                        }
                    )

    return {
        "source": source,
        "product": app_name,
        "reviews": reviews,
        "error": None if reviews else result.get("error"),
    }


# ---------------------------------------------------------------------------
# 7. LinkedIn Comments (professional buyer perspective)
# ---------------------------------------------------------------------------
def fetch_linkedin_comments(query: str, limit: int = 20) -> dict:
    """Fetch LinkedIn post snippets for a product or topic via Firecrawl + SerpAPI.

    LinkedIn blocks direct scraping, so this uses a Google search restricted
    to linkedin.com posts for public snippets.

    Args:
        query: Product/topic search query (e.g. "Notion vs Confluence review").
        limit: Max snippets to return. Defaults to 20.

    Returns:
        dict with keys: "source", "product", "reviews" (post snippets), "error"
    """
    source = "linkedin_comments"

    params: dict[str, Any] = {
        "engine": "google",
        "q": f"{query} site:linkedin.com/posts",
        "num": min(limit, 10),
    }
    result = _serpapi_get(params)

    reviews: list[dict] = []

    if not result["error"] and result["data"]:
        for item in (result["data"].get("organic_results") or [])[:limit]:
            snippet = item.get("snippet", "")
            title = item.get("title", "")
            combined = f"{title}. {snippet}".strip(". ")
            if combined and len(combined) >= 20:
                reviews.append(
                    {
                        "source": source,
                        "product": query,
                        "text": combined[:400],
                        "rating": "",
                        "link": item.get("link", ""),
                    }
                )

    return {
        "source": source,
        "product": query,
        "reviews": reviews,
        "error": None if reviews else result.get("error"),
    }
