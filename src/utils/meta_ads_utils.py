"""
Meta Ad Library Utility — Official Meta Ads Archive API.

Provides:
  - Structured JSON for political ads, EU-regulated ads, ad spend ranges,
    demographic distribution, and regional targeting data.
  - ~200 calls/hour on the free tier.
  - Requires identity verification via Meta Business Manager before use.

Environment variable required:
  META_AD_LIBRARY_ACCESS_TOKEN  — App or user access token with
                                   ads_read permission and identity verified.

Meta Graph API reference:
  https://developers.facebook.com/docs/marketing-api/reference/ads_archive/
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
META_ADS_ARCHIVE_URL = "https://graph.facebook.com/v21.0/ads_archive"

# Core fields returned for every ad — extend as needed within API limits
_DEFAULT_FIELDS = ",".join(
    [
        "id",
        "page_id",
        "page_name",
        "ad_creative_bodies",
        "ad_creative_link_captions",
        "ad_creative_link_descriptions",
        "ad_creative_link_titles",
        "ad_delivery_start_time",
        "ad_delivery_stop_time",
        "ad_snapshot_url",
        "currency",
        "demographic_distribution",
        "funding_entity",
        "impressions",
        "region_distribution",
        "spend",
        "languages",
        "publisher_platforms",
    ]
)

# Supported ad_type values
AD_TYPES = (
    "ALL",
    "POLITICAL_AND_ISSUE_ADS",
    "HOUSING_ADS",
    "EMPLOYMENT_ADS",
    "CREDIT_ADS",
)


# ---------------------------------------------------------------------------
# Core fetch function
# ---------------------------------------------------------------------------
def fetch_meta_ads(
    search_terms: str,
    country_codes: list[str] | None = None,
    ad_type: str = "ALL",
    limit: int = 50,
    fields: str | None = None,
    after_cursor: str | None = None,
) -> dict:
    """Fetch ads from the Meta Ad Library Archive API.

    Args:
        search_terms:  Brand name, keywords, or advertiser to search for.
        country_codes: ISO-3166-1 alpha-2 codes, e.g. ["US", "GB", "DE"].
                       Defaults to ["US"] if omitted.
        ad_type:       One of AD_TYPES. Defaults to "ALL".
        limit:         Max ads per page (1–100). Defaults to 50.
        fields:        Comma-separated API fields. Defaults to _DEFAULT_FIELDS.
        after_cursor:  Pagination cursor from a previous response.

    Returns:
        dict with keys:
          "ads"         — list of ad objects
          "paging"      — pagination cursors (before/after)
          "total_count" — estimated total (may be None if unavailable)
          "error"       — error string if the call failed, else None
    """
    token = os.getenv("META_AD_LIBRARY_ACCESS_TOKEN")
    if not token:
        return _error_result("META_AD_LIBRARY_ACCESS_TOKEN not set in environment.")

    if ad_type not in AD_TYPES:
        return _error_result(f"Invalid ad_type '{ad_type}'. Choose from: {AD_TYPES}")

    params: dict = {
        "access_token": token,
        "search_terms": search_terms,
        "ad_type": ad_type,
        "fields": fields or _DEFAULT_FIELDS,
        "limit": min(max(1, limit), 100),
    }

    if country_codes:
        params["ad_reached_countries"] = ",".join(c.upper() for c in country_codes)
    else:
        params["ad_reached_countries"] = "US"

    if after_cursor:
        params["after"] = after_cursor

    try:
        resp = requests.get(META_ADS_ARCHIVE_URL, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        ads = payload.get("data", [])
        paging = payload.get("paging", {})
        total = payload.get("count", None)

        return {
            "ads": ads,
            "paging": paging,
            "total_count": total,
            "error": None,
        }

    except requests.exceptions.HTTPError as exc:
        # Surface Meta API error messages for debugging
        try:
            err_body = exc.response.json()
            msg = err_body.get("error", {}).get("message", str(exc))
        except Exception:
            msg = str(exc)
        return _error_result(f"Meta API HTTP error: {msg}")
    except Exception as exc:
        return _error_result(f"Meta API request failed: {exc}")


# ---------------------------------------------------------------------------
# Convenience: paginated fetch (auto-follows cursors up to max_pages)
# ---------------------------------------------------------------------------
def fetch_meta_ads_paginated(
    search_terms: str,
    country_codes: list[str] | None = None,
    ad_type: str = "ALL",
    limit_per_page: int = 50,
    max_pages: int = 4,
    fields: str | None = None,
    sleep_between_pages: float = 0.5,
) -> dict:
    """Fetch multiple pages of Meta ads, respecting the ~200 calls/hr rate limit.

    Args:
        search_terms:       Advertiser / keyword to search.
        country_codes:      ISO country codes. Defaults to ["US"].
        ad_type:            One of AD_TYPES.
        limit_per_page:     Ads per API call (max 100).
        max_pages:          Safety cap on total pages fetched.
        fields:             API fields string.
        sleep_between_pages: Seconds to sleep between pages (rate-limit courtesy).

    Returns:
        dict with keys:
          "ads"         — combined list of all ad objects across pages
          "pages_fetched"
          "error"       — first error encountered, or None
    """
    all_ads: list[dict] = []
    cursor: str | None = None
    pages = 0

    while pages < max_pages:
        result = fetch_meta_ads(
            search_terms=search_terms,
            country_codes=country_codes,
            ad_type=ad_type,
            limit=limit_per_page,
            fields=fields,
            after_cursor=cursor,
        )

        if result["error"]:
            return {"ads": all_ads, "pages_fetched": pages, "error": result["error"]}

        all_ads.extend(result["ads"])
        pages += 1

        # Check for next page cursor
        next_cursor = result["paging"].get("cursors", {}).get("after")
        if not next_cursor or not result["ads"]:
            break

        cursor = next_cursor
        if pages < max_pages:
            time.sleep(sleep_between_pages)

    return {"ads": all_ads, "pages_fetched": pages, "error": None}


# ---------------------------------------------------------------------------
# Summariser — collapses raw ads into a concise analytics dict for the LLM
# ---------------------------------------------------------------------------
def summarise_meta_ads(ads: list[dict]) -> dict:
    """Build a concise analytics summary from raw Meta Ad Library ad objects.

    Extracts spend ranges, impression buckets, demographic breakdowns,
    active vs. stopped ratios, and top page/funder names.

    Args:
        ads: Raw ad objects returned by fetch_meta_ads / fetch_meta_ads_paginated.

    Returns:
        Analytics summary dict ready to be serialised and handed to the LLM.
    """
    if not ads:
        return {"total_ads": 0, "summary": "No ads returned."}

    spend_buckets: dict[str, int] = {}
    impression_buckets: dict[str, int] = {}
    demographics: dict[str, dict[str, float]] = {"age": {}, "gender": {}}
    page_names: dict[str, int] = {}
    funders: dict[str, int] = {}
    active_count = 0

    for ad in ads:
        # Spend
        spend = ad.get("spend") or {}
        bucket = _spend_label(spend)
        spend_buckets[bucket] = spend_buckets.get(bucket, 0) + 1

        # Impressions
        imp = ad.get("impressions") or {}
        imp_bucket = _impression_label(imp)
        impression_buckets[imp_bucket] = impression_buckets.get(imp_bucket, 0) + 1

        # Demographics
        for demo in ad.get("demographic_distribution") or []:
            age = demo.get("age", "unknown")
            gender = demo.get("gender", "unknown")
            pct = float(demo.get("percentage", 0))
            demographics["age"][age] = demographics["age"].get(age, 0.0) + pct
            demographics["gender"][gender] = (
                demographics["gender"].get(gender, 0.0) + pct
            )

        # Page names
        pn = ad.get("page_name", "Unknown")
        page_names[pn] = page_names.get(pn, 0) + 1

        # Funders
        fn = ad.get("funding_entity", "Unknown")
        if fn:
            funders[fn] = funders.get(fn, 0) + 1

        # Active status
        if not ad.get("ad_delivery_stop_time"):
            active_count += 1

    return {
        "total_ads": len(ads),
        "active_ads": active_count,
        "stopped_ads": len(ads) - active_count,
        "spend_distribution": spend_buckets,
        "impression_distribution": impression_buckets,
        "demographic_distribution": {
            "age": _normalise_dict(demographics["age"]),
            "gender": _normalise_dict(demographics["gender"]),
        },
        "top_pages": dict(sorted(page_names.items(), key=lambda x: -x[1])[:10]),
        "top_funders": dict(sorted(funders.items(), key=lambda x: -x[1])[:10]),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _error_result(msg: str) -> dict:
    return {"ads": [], "paging": {}, "total_count": None, "error": msg}


def _spend_label(spend: dict) -> str:
    lower = spend.get("lower_bound", "?")
    upper = spend.get("upper_bound", "?")
    return f"${lower}–${upper}" if lower != "?" or upper != "?" else "unknown"


def _impression_label(impressions: dict) -> str:
    lower = impressions.get("lower_bound", "?")
    upper = impressions.get("upper_bound", "?")
    return f"{lower}–{upper}" if lower != "?" or upper != "?" else "unknown"


def _normalise_dict(d: dict[str, float]) -> dict[str, float]:
    total = sum(d.values())
    if total == 0:
        return d
    return {
        k: round(v / total * 100, 1) for k, v in sorted(d.items(), key=lambda x: -x[1])
    }
