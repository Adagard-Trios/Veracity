"""
SerpAPI Utility — Google Ads Transparency, Trends, and News as structured JSON.

Provides:
  - Google Ads Transparency Center: sponsored content per advertiser.
  - Google Trends: interest-over-time and rising queries.
  - Google News: recent editorial coverage for a query.

Free tier: up to 100 searches/month (no scraping — official structured JSON).

Environment variable required:
  SERPAPI_API_KEY  — obtained from https://serpapi.com/

SerpAPI Python SDK:
  pip install google-search-results

Fallback: if the SDK is unavailable, direct HTTP calls to serpapi.com are used.
"""

from __future__ import annotations

import os
from typing import Any
from dotenv import load_dotenv

load_dotenv()

_SERPAPI_BASE = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Internal HTTP helper (avoids hard dependency on the SDK for basic usage)
# ---------------------------------------------------------------------------
def _serpapi_get(params: dict) -> dict:
    """Execute a SerpAPI GET request and return parsed JSON.

    Tries the official `serpapi` SDK first; falls back to raw requests.
    """
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return {"error": "SERPAPI_API_KEY not set in environment.", "data": None}

    params["api_key"] = api_key

    # Try SDK
    try:
        from serpapi import GoogleSearch  # type: ignore

        client = GoogleSearch(params)
        result = client.get_dict()
        if "error" in result:
            return {"error": result["error"], "data": None}
        return {"error": None, "data": result}
    except ImportError:
        pass  # fall through to requests

    # Fallback: raw HTTP
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
# 1. Google Ads Transparency Center
# ---------------------------------------------------------------------------
def google_ads_transparency(
    advertiser: str,
    region: str = "US",
    limit: int = 20,
) -> dict:
    """Fetch sponsored ads for an advertiser from Google Ads Transparency Center.

    Args:
        advertiser: Company / brand name to look up.
        region:     Two-letter country code (e.g. "US", "DE"). Defaults to "US".
        limit:      Max number of ad results to return.

    Returns:
        dict with keys:
          "advertiser"     — query used
          "ads"            — list of ad objects (title, description, domain, format)
          "total_results"  — estimated count
          "error"          — error string or None
    """
    params: dict[str, Any] = {
        "engine": "google_ads_transparency_center",
        "advertiser_name": advertiser,
        "region": region,
        "num": min(limit, 100),
    }
    result = _serpapi_get(params)

    if result["error"]:
        return {
            "advertiser": advertiser,
            "ads": [],
            "total_results": 0,
            "error": result["error"],
        }

    data = result["data"] or {}
    raw_ads = data.get("ads", [])

    ads = []
    for ad in raw_ads[:limit]:
        ads.append(
            {
                "title": ad.get("title", ""),
                "description": ad.get("description", ""),
                "domain": ad.get("domain", ""),
                "displayed_url": ad.get("displayed_link", ""),
                "format": ad.get("ad_type", "text"),
                "last_shown": ad.get("last_shown_date", ""),
            }
        )

    return {
        "advertiser": advertiser,
        "ads": ads,
        "total_results": data.get("search_information", {}).get(
            "total_results", len(ads)
        ),
        "error": None,
    }


# ---------------------------------------------------------------------------
# 2. Google Trends
# ---------------------------------------------------------------------------
def google_trends(
    keywords: list[str],
    timeframe: str = "today 12-m",
    geo: str = "US",
    category: int = 0,
) -> dict:
    """Fetch Google Trends interest-over-time and related/rising queries.

    Args:
        keywords:  Up to 5 keywords to compare trends for.
        timeframe: Time range string (e.g. "today 12-m", "today 5-y",
                   "2023-01-01 2024-01-01"). Defaults to last 12 months.
        geo:       Two-letter country code or "" for worldwide. Defaults to "US".
        category:  Google Trends category ID (0 = all categories).

    Returns:
        dict with keys:
          "keywords"         — list of queried keywords
          "interest_over_time" — list of {date, values} dicts
          "related_queries"  — {keyword: {top: [...], rising: [...]}} mapping
          "error"            — error string or None
    """
    if not keywords:
        return {
            "keywords": [],
            "interest_over_time": [],
            "related_queries": {},
            "error": "No keywords provided.",
        }

    params: dict[str, Any] = {
        "engine": "google_trends",
        "q": ",".join(keywords[:5]),
        "date": timeframe,
        "geo": geo,
        "cat": category,
        "data_type": "TIMESERIES",
    }
    result = _serpapi_get(params)

    if result["error"]:
        return {
            "keywords": keywords,
            "interest_over_time": [],
            "related_queries": {},
            "error": result["error"],
        }

    data = result["data"] or {}

    # Interest over time
    iot_raw = data.get("interest_over_time", {}).get("timeline_data", [])
    interest_over_time = []
    for point in iot_raw:
        values = {}
        for v in point.get("values", []):
            values[v.get("query", "")] = v.get("value", 0)
        interest_over_time.append({"date": point.get("date", ""), "values": values})

    # Related queries
    related_queries: dict = {}
    rq_raw = data.get("related_queries", {})
    for kw, qdata in rq_raw.items():
        related_queries[kw] = {
            "top": [
                {"query": q.get("query", ""), "value": q.get("value", 0)}
                for q in qdata.get("top", [])[:10]
            ],
            "rising": [
                {"query": q.get("query", ""), "value": q.get("value", "Breakout")}
                for q in qdata.get("rising", [])[:10]
            ],
        }

    # Also fetch related topics if we have a single keyword
    if len(keywords) == 1:
        topics_params = {**params, "data_type": "RELATED_TOPICS"}
        topics_result = _serpapi_get(topics_params)
        if not topics_result["error"] and topics_result["data"]:
            related_queries["_topics"] = topics_result["data"].get("related_topics", {})

    return {
        "keywords": keywords,
        "interest_over_time": interest_over_time,
        "related_queries": related_queries,
        "error": None,
    }


# ---------------------------------------------------------------------------
# 3. Google News
# ---------------------------------------------------------------------------
def google_news(
    query: str,
    recency: str = "qdr:w",
    num: int = 20,
    language: str = "en",
    country: str = "us",
) -> dict:
    """Search Google News for recent coverage of a brand or topic.

    Args:
        query:    Search query (brand name, product, event, etc.).
        recency:  Google time filter. Common values:
                    "qdr:d" = past day, "qdr:w" = past week,
                    "qdr:m" = past month, "qdr:y" = past year.
                  Defaults to past week.
        num:      Max articles to return (1–100). Defaults to 20.
        language: Language code for results (e.g. "en"). Defaults to "en".
        country:  Country code for results (e.g. "us"). Defaults to "us".

    Returns:
        dict with keys:
          "query"        — search query used
          "articles"     — list of article objects (title, source, date, snippet, link)
          "total_count"  — estimated total from Google
          "error"        — error string or None
    """
    params: dict[str, Any] = {
        "engine": "google_news",
        "q": query,
        "tbs": recency,
        "num": min(num, 100),
        "hl": language,
        "gl": country,
    }
    result = _serpapi_get(params)

    if result["error"]:
        return {
            "query": query,
            "articles": [],
            "total_count": 0,
            "error": result["error"],
        }

    data = result["data"] or {}
    raw_results = data.get("news_results", [])

    articles = []
    for item in raw_results[:num]:
        articles.append(
            {
                "title": item.get("title", ""),
                "source": item.get("source", {}).get("name", "")
                if isinstance(item.get("source"), dict)
                else item.get("source", ""),
                "date": item.get("date", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "thumbnail": item.get("thumbnail", ""),
            }
        )

    return {
        "query": query,
        "articles": articles,
        "total_count": data.get("search_information", {}).get(
            "total_results", len(articles)
        ),
        "error": None,
    }


# ---------------------------------------------------------------------------
# 4. Google Search (general — for ad copy / landing pages)
# ---------------------------------------------------------------------------
def google_search_ads(
    query: str,
    num: int = 10,
    country: str = "us",
) -> dict:
    """Run a regular Google search and extract paid ad results.

    Useful for capturing live ad copy and landing pages for a competitor brand.

    Args:
        query:   Search query (e.g. "best project management software").
        num:     Max organic + ad results to retrieve.
        country: Country code for the SERP. Defaults to "us".

    Returns:
        dict with keys:
          "query"          — search query used
          "paid_ads"       — list of {title, description, link, displayed_url}
          "organic_top5"   — top 5 organic results for context
          "error"          — error string or None
    """
    params: dict[str, Any] = {
        "engine": "google",
        "q": query,
        "num": num,
        "gl": country,
        "hl": "en",
    }
    result = _serpapi_get(params)

    if result["error"]:
        return {
            "query": query,
            "paid_ads": [],
            "organic_top5": [],
            "error": result["error"],
        }

    data = result["data"] or {}

    paid_ads = []
    for ad in data.get("ads", []):
        paid_ads.append(
            {
                "title": ad.get("title", ""),
                "description": ad.get("description", ""),
                "link": ad.get("link", ""),
                "displayed_url": ad.get("displayed_link", ""),
                "sitelinks": [s.get("title", "") for s in ad.get("sitelinks", [])],
            }
        )

    organic = []
    for res in (data.get("organic_results") or [])[:5]:
        organic.append(
            {
                "title": res.get("title", ""),
                "link": res.get("link", ""),
                "snippet": res.get("snippet", ""),
                "position": res.get("position", 0),
            }
        )

    return {
        "query": query,
        "paid_ads": paid_ads,
        "organic_top5": organic,
        "error": None,
    }
