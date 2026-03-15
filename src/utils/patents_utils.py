"""
USPTO Patents Utility — Pre-launch technical signal via patent filings.

Uses the USPTO PatentsView API (no API key required for standard usage):
  https://search.patentsview.org/api/v1/patent/

Also supports the USPTO EFTS (Elasticsearch Full-Text Search) for broader
free-text queries against patent titles, abstracts, and claims:
  https://efts.uspto.gov/LATEST/search-fields

Patent data provides early technical signal for:
  - Competitor R&D direction (filed before products launch)
  - Technology landscape mapping
  - IP risk assessment
  - "Unfair advantage" detection (rare patented tech moats)

No authentication or API key required for either endpoint.
"""

from __future__ import annotations

import json
import urllib.parse
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"
_EFTS_SEARCH_URL = "https://efts.uspto.gov/LATEST/search-fields"

_DEFAULT_PATENT_FIELDS = [
    "patent_id",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_type",
    "inventors",
    "assignees",
    "cpc_at_issue",
    "uspc_at_issue",
]


# ---------------------------------------------------------------------------
# PatentsView API
# ---------------------------------------------------------------------------
def search_patents(
    query: str,
    assignee: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    fields: list[str] | None = None,
) -> dict:
    """Search patents via the USPTO PatentsView API.

    Args:
        query:      Free-text query applied to patent title AND abstract.
        assignee:   Optional company / assignee name to filter by.
                    E.g. "Apple Inc", "Google LLC".
        date_from:  ISO date string (YYYY-MM-DD) — earliest grant date.
        date_to:    ISO date string (YYYY-MM-DD) — latest grant date.
        limit:      Max patents to return (1–100). Defaults to 20.
        fields:     List of PatentsView fields to retrieve.
                    Defaults to _DEFAULT_PATENT_FIELDS.

    Returns:
        dict with keys:
          "query"       — query used
          "patents"     — list of patent objects
          "total_count" — total matching patents (may exceed limit)
          "error"       — error string or None
    """
    # Build the PatentsView query object (AND logic)
    clauses: list[dict] = []

    if query:
        # Title OR abstract full-text match
        clauses.append(
            {
                "_or": [
                    {"_text_any": {"patent_title": query}},
                    {"_text_any": {"patent_abstract": query}},
                ]
            }
        )

    if assignee:
        clauses.append({"_contains": {"assignee_organization": assignee}})

    if date_from:
        clauses.append({"_gte": {"patent_date": date_from}})

    if date_to:
        clauses.append({"_lte": {"patent_date": date_to}})

    pv_query: dict
    if len(clauses) == 0:
        return {
            "query": query,
            "patents": [],
            "total_count": 0,
            "error": "No query terms provided.",
        }
    elif len(clauses) == 1:
        pv_query = clauses[0]
    else:
        pv_query = {"_and": clauses}

    payload = {
        "q": json.dumps(pv_query),
        "f": json.dumps(fields or _DEFAULT_PATENT_FIELDS),
        "o": json.dumps({"patent_date": "desc"}),
        "per_page": min(limit, 100),
        "page": 1,
    }

    try:
        resp = requests.get(_PATENTSVIEW_URL, params=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        raw_patents = data.get("patents") or []
        total = data.get("total_patent_count", len(raw_patents))

        patents = _normalise_patents(raw_patents)
        return {"query": query, "patents": patents, "total_count": total, "error": None}

    except requests.exceptions.HTTPError as exc:
        try:
            msg = exc.response.json().get("message", str(exc))
        except Exception:
            msg = str(exc)
        return {
            "query": query,
            "patents": [],
            "total_count": 0,
            "error": f"PatentsView HTTP error: {msg}",
        }
    except Exception as exc:
        return {"query": query, "patents": [], "total_count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# EFTS full-text search (broader free-text, includes claims)
# ---------------------------------------------------------------------------
def search_patents_efts(
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> dict:
    """Full-text patent search via USPTO EFTS (Elasticsearch).

    Searches patent titles, abstracts, AND claims — more comprehensive
    than PatentsView for broad concept discovery.

    Args:
        query:     Natural-language or keyword query.
        date_from: ISO date string (YYYY-MM-DD) — earliest filing date.
        date_to:   ISO date string (YYYY-MM-DD) — latest filing date.
        limit:     Max results to return.

    Returns:
        dict with keys:
          "query"       — query used
          "patents"     — list of patent summaries
          "total_count" — total matching docs
          "error"       — error string or None
    """
    params: dict = {
        "q": query,
        "dateRangeField": "patent_date",
        "hits.hits.total.value": limit,
        "_source": "patent_id,patent_title,patent_date,inventors,assignees,abstract",
    }

    if date_from:
        params["dateRangeStart"] = date_from
    if date_to:
        params["dateRangeEnd"] = date_to

    try:
        resp = requests.get(_EFTS_SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {}).get("value", 0)

        patents = []
        for hit in hits[:limit]:
            src = hit.get("_source", {})
            patents.append(
                {
                    "patent_id": src.get("patent_id", hit.get("_id", "")),
                    "title": src.get("patent_title", ""),
                    "abstract": (src.get("abstract") or "")[:400],
                    "date": src.get("patent_date", ""),
                    "inventors": _format_inventors(src.get("inventors", [])),
                    "assignees": _format_assignees(src.get("assignees", [])),
                }
            )

        return {"query": query, "patents": patents, "total_count": total, "error": None}

    except Exception as exc:
        return {"query": query, "patents": [], "total_count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Convenience: search by assignee (company competitive patent map)
# ---------------------------------------------------------------------------
def get_company_patents(
    company: str,
    years_back: int = 3,
    limit: int = 30,
) -> dict:
    """Retrieve recent patents assigned to a specific company.

    Useful for mapping competitor R&D focus areas.

    Args:
        company:    Exact or partial company name (e.g. "OpenAI", "Anthropic").
        years_back: How many years of patent history to fetch.
        limit:      Max patents to return.

    Returns:
        dict with same structure as search_patents(), plus a "cpc_summary"
        key showing the top CPC technology classifications for the company.
    """
    from datetime import date, timedelta  # noqa: PLC0415

    date_from = (date.today() - timedelta(days=years_back * 365)).isoformat()

    result = search_patents(
        query="",
        assignee=company,
        date_from=date_from,
        limit=limit,
    )

    if result["patents"]:
        result["cpc_summary"] = _summarise_cpc(result["patents"])

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _normalise_patents(raw: list[dict]) -> list[dict]:
    """Flatten the nested PatentsView response into a simpler structure."""
    out = []
    for p in raw:
        # Inventors — nested list of dicts
        inventors = []
        for inv in p.get("inventors") or []:
            name = f"{inv.get('inventor_name_first', '')} {inv.get('inventor_name_last', '')}".strip()
            if name:
                inventors.append(name)

        # Assignees
        assignees = []
        for asgn in p.get("assignees") or []:
            org = asgn.get("assignee_organization", "")
            if org:
                assignees.append(org)

        # CPC classifications
        cpcs = []
        for c in p.get("cpc_at_issue") or []:
            code = c.get("cpc_subgroup_id", "")
            if code:
                cpcs.append(code)

        out.append(
            {
                "patent_id": p.get("patent_id", ""),
                "title": p.get("patent_title", ""),
                "abstract": (p.get("patent_abstract") or "")[:400],
                "date": p.get("patent_date", ""),
                "type": p.get("patent_type", ""),
                "inventors": inventors,
                "assignees": assignees,
                "cpc_codes": cpcs[:5],
            }
        )
    return out


def _format_inventors(raw: list) -> list[str]:
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return [
            f"{r.get('inventor_name_first', '')} {r.get('inventor_name_last', '')}".strip()
            for r in raw
        ]
    return [str(r) for r in raw]


def _format_assignees(raw: list) -> list[str]:
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return [r.get("assignee_organization", str(r)) for r in raw]
    return [str(r) for r in raw]


def _summarise_cpc(patents: list[dict]) -> dict[str, int]:
    """Count CPC code prefix frequency to identify dominant R&D themes."""
    counts: dict[str, int] = {}
    for p in patents:
        for code in p.get("cpc_codes", []):
            prefix = code[:4]  # e.g. "G06F" from "G06F17/00"
            counts[prefix] = counts.get(prefix, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:15])
