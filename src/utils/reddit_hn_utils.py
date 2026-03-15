"""
Reddit + HN Algolia Utility — Real user voice and community signals.

Reddit:
  - Public JSON API (no auth required for basic searches).
  - Optional OAuth2 for higher rate limits: set REDDIT_CLIENT_ID and
    REDDIT_CLIENT_SECRET in .env (register a "script" app at
    https://www.reddit.com/prefs/apps).
  - Endpoints used:
      https://www.reddit.com/search.json?q=...   (cross-subreddit)
      https://www.reddit.com/r/{sub}/search.json  (subreddit-scoped)

HN Algolia (Hacker News):
  - Free, no API key required.
  - Full-text search across stories, comments, Ask HN, Show HN.
  - Endpoint: https://hn.algolia.com/api/v1/search?query=...

Both are open data — ideal for capturing authentic user voice, sentiment,
and early technical signals before mainstream coverage.
"""

from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
_REDDIT_SUBREDDIT_SEARCH_URL = "https://www.reddit.com/r/{sub}/search.json"
_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"
_HN_ALGOLIA_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"

_DEFAULT_HEADERS = {
    "User-Agent": os.getenv(
        "REDDIT_USER_AGENT", "veracity-marketing-agent/1.0 (research bot)"
    ),
}


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------
def fetch_reddit_posts(
    query: str,
    subreddits: list[str] | None = None,
    sort: str = "relevance",
    time_filter: str = "month",
    limit: int = 25,
) -> dict:
    """Search Reddit for posts matching a query.

    Tries OAuth2 if credentials are available; falls back to the public
    JSON API if not.

    Args:
        query:       Search query (brand name, topic, product).
        subreddits:  Optional list of subreddits to scope the search.
                     If None, searches all of Reddit (cross-subreddit).
        sort:        "relevance" | "hot" | "top" | "new" | "comments".
        time_filter: "hour" | "day" | "week" | "month" | "year" | "all".
        limit:       Max posts to return (1–100).

    Returns:
        dict with keys:
          "query"    — search query used
          "posts"    — list of post objects
          "error"    — error string or None
    """
    token = _get_reddit_token()
    posts: list[dict] = []
    errors: list[str] = []

    if subreddits:
        for sub in subreddits:
            result = _search_subreddit(query, sub, sort, time_filter, limit, token)
            if result["error"]:
                errors.append(result["error"])
            posts.extend(result["posts"])
    else:
        result = _search_all_reddit(query, sort, time_filter, limit, token)
        if result["error"]:
            errors.append(result["error"])
        posts.extend(result["posts"])

    # Deduplicate by post ID
    seen: set[str] = set()
    unique_posts: list[dict] = []
    for p in posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique_posts.append(p)

    return {
        "query": query,
        "posts": unique_posts[:limit],
        "error": "; ".join(errors) if errors else None,
    }


def fetch_reddit_comments(
    query: str,
    subreddits: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """Search Reddit comments for a query — captures user voice beyond post titles.

    Args:
        query:      Search query.
        subreddits: Optional subreddit filter list.
        limit:      Max comments to return.

    Returns:
        dict with keys:
          "query"    — search query used
          "comments" — list of comment objects (body, score, subreddit, link)
          "error"    — error string or None
    """
    token = _get_reddit_token()
    # Reddit's search can be scoped to comments with type=comment
    params: dict = {
        "q": query,
        "type": "comment",
        "sort": "relevance",
        "t": "month",
        "limit": min(limit, 100),
    }

    if subreddits:
        params["restrict_sr"] = "true"

    url = _REDDIT_SEARCH_URL
    headers = dict(_DEFAULT_HEADERS)
    if token:
        url = "https://oauth.reddit.com/search"
        headers["Authorization"] = f"bearer {token}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        comments = []
        for child in children:
            d = child.get("data", {})
            comments.append(
                {
                    "id": d.get("id", ""),
                    "body": (d.get("body", "") or "")[:500],
                    "score": d.get("score", 0),
                    "subreddit": d.get("subreddit", ""),
                    "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
                    "created_utc": d.get("created_utc", 0),
                }
            )
        return {"query": query, "comments": comments, "error": None}
    except Exception as exc:
        return {"query": query, "comments": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# HN Algolia
# ---------------------------------------------------------------------------
def fetch_hn_stories(
    query: str,
    limit: int = 20,
    search_by_date: bool = False,
    tags: str = "story",
    num_days_back: int = 90,
) -> dict:
    """Search Hacker News via the Algolia API.

    No API key required. Returns stories, Ask HN, Show HN posts.

    Args:
        query:          Full-text search query.
        limit:          Max results to return.
        search_by_date: If True, sorts by date (latest first) instead of relevance.
        tags:           Algolia tag filter. E.g.: "story", "comment",
                        "ask_hn", "show_hn", "story,ask_hn".
        num_days_back:  Only return results from the last N days.
                        Set to 0 to disable the filter.

    Returns:
        dict with keys:
          "query"   — search query
          "stories" — list of story objects
          "nbHits"  — total hits from Algolia
          "error"   — error string or None
    """
    base_url = _HN_ALGOLIA_DATE_URL if search_by_date else _HN_ALGOLIA_URL

    params: dict = {
        "query": query,
        "tags": tags,
        "hitsPerPage": min(limit, 100),
    }

    if num_days_back > 0:
        cutoff = int(time.time()) - (num_days_back * 86_400)
        params["numericFilters"] = f"created_at_i>{cutoff}"

    try:
        resp = requests.get(base_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("hits", [])
        stories: list[dict] = []

        for hit in hits[:limit]:
            stories.append(
                {
                    "objectID": hit.get("objectID", ""),
                    "title": hit.get("title", hit.get("story_title", "")),
                    "url": hit.get("url", ""),
                    "author": hit.get("author", ""),
                    "points": hit.get("points", 0),
                    "num_comments": hit.get("num_comments", 0),
                    "created_at": hit.get("created_at", ""),
                    "story_text": (hit.get("story_text") or "")[:400],
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                }
            )

        return {
            "query": query,
            "stories": stories,
            "nbHits": data.get("nbHits", len(stories)),
            "error": None,
        }

    except Exception as exc:
        return {"query": query, "stories": [], "nbHits": 0, "error": str(exc)}


def fetch_hn_comments(query: str, limit: int = 30, num_days_back: int = 90) -> dict:
    """Search HN comments for a query — raw community reaction.

    Args:
        query:        Full-text search query.
        limit:        Max comments to return.
        num_days_back: Only return comments from the last N days.

    Returns:
        dict with keys:
          "query"    — search query
          "comments" — list of comment objects
          "error"    — error string or None
    """
    return fetch_hn_stories(
        query=query,
        limit=limit,
        tags="comment",
        num_days_back=num_days_back,
    )


# ---------------------------------------------------------------------------
# Private: Reddit auth helpers
# ---------------------------------------------------------------------------
def _get_reddit_token() -> str | None:
    """Obtain a Reddit OAuth2 bearer token if credentials are configured."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    try:
        resp = requests.post(
            _REDDIT_TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers=_DEFAULT_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception:
        return None


def _search_all_reddit(
    query: str,
    sort: str,
    time_filter: str,
    limit: int,
    token: str | None,
) -> dict:
    url = _REDDIT_SEARCH_URL
    headers = dict(_DEFAULT_HEADERS)
    if token:
        url = "https://oauth.reddit.com/search"
        headers["Authorization"] = f"bearer {token}"

    params: dict = {
        "q": query,
        "sort": sort,
        "t": time_filter,
        "limit": min(limit, 100),
        "type": "link",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return {"posts": _parse_reddit_posts(resp.json()), "error": None}
    except Exception as exc:
        return {"posts": [], "error": str(exc)}


def _search_subreddit(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int,
    token: str | None,
) -> dict:
    url = _REDDIT_SUBREDDIT_SEARCH_URL.format(sub=subreddit)
    headers = dict(_DEFAULT_HEADERS)
    if token:
        url = f"https://oauth.reddit.com/r/{subreddit}/search"
        headers["Authorization"] = f"bearer {token}"

    params: dict = {
        "q": query,
        "sort": sort,
        "t": time_filter,
        "limit": min(limit, 100),
        "restrict_sr": "true",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return {"posts": _parse_reddit_posts(resp.json()), "error": None}
    except Exception as exc:
        return {"posts": [], "error": str(exc)}


def _parse_reddit_posts(data: dict) -> list[dict]:
    children = data.get("data", {}).get("children", [])
    posts = []
    for child in children:
        d = child.get("data", {})
        posts.append(
            {
                "id": d.get("id", ""),
                "title": d.get("title", ""),
                "subreddit": d.get("subreddit", ""),
                "author": d.get("author", ""),
                "score": d.get("score", 0),
                "upvote_ratio": d.get("upvote_ratio", 0.0),
                "num_comments": d.get("num_comments", 0),
                "selftext": (d.get("selftext") or "")[:600],
                "url": d.get("url", ""),
                "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
                "created_utc": d.get("created_utc", 0),
                "flair": d.get("link_flair_text", ""),
            }
        )
    return posts
