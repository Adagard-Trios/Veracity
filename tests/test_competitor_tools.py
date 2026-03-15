"""
tests/test_competitor_tools.py

Unit tests for competitor_tools.py — Firecrawl calls are MOCKED so
no Firecrawl credits are consumed.

Run: pytest tests/test_competitor_tools.py -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_firecrawl_response(extract_data):
    """Build a fake httpx Response object that Firecrawl would return."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "data": {"extract": extract_data},
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# fetch_competitor_website
# ---------------------------------------------------------------------------

class TestFetchCompetitorWebsite:

    def test_returns_json_string(self):
        from src.nodes.competitor_tools import fetch_competitor_website

        mock_extract = {
            "company_tagline": "AI sales platform",
            "features": ["email", "CRM"],
            "pricing_tier": "freemium",
            "target_customer": "Sales teams",
            "positioning_keywords": ["AI", "sales"],
        }
        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response(mock_extract)):
            result = fetch_competitor_website.invoke({
                "competitor_name": "Apollo.io",
                "website_url": "https://www.apollo.io",
            })

        data = json.loads(result)
        assert data["competitor"] == "Apollo.io"
        assert data["url"] == "https://www.apollo.io"
        assert data["confidence"] == 0.85
        assert "data" in data

    def test_returns_low_confidence_on_empty_extract(self):
        from src.nodes.competitor_tools import fetch_competitor_website

        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response({})):
            result = fetch_competitor_website.invoke({
                "competitor_name": "Unknown",
                "website_url": "https://example.com",
            })

        data = json.loads(result)
        assert data["confidence"] == 0.3

    def test_handles_firecrawl_error_gracefully(self):
        from src.nodes.competitor_tools import fetch_competitor_website
        import httpx

        with patch("src.nodes.competitor_tools.httpx.post",
                   side_effect=httpx.HTTPStatusError(
                       "429", request=MagicMock(), response=MagicMock()
                   )):
            result = fetch_competitor_website.invoke({
                "competitor_name": "Broken",
                "website_url": "https://broken.example.com",
            })

        data = json.loads(result)
        assert data["confidence"] == 0.0
        assert "error" in data

    def test_missing_env_key_raises(self, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        from src.nodes import competitor_tools
        # Re-import to pick up env change
        import importlib
        importlib.reload(competitor_tools)
        with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
            competitor_tools._firecrawl_api_key()


# ---------------------------------------------------------------------------
# fetch_competitor_changelog
# ---------------------------------------------------------------------------

class TestFetchCompetitorChangelog:

    def test_returns_recent_launches(self):
        from src.nodes.competitor_tools import fetch_competitor_changelog

        launches = [
            {"date": "2026-01", "title": "Feature A", "description": "New thing"},
            {"date": "2026-02", "title": "Feature B", "description": "Other thing"},
        ]
        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response(launches)):
            result = fetch_competitor_changelog.invoke({
                "competitor_name": "Apollo.io",
                "changelog_url": "https://apollo.io/changelog",
            })

        data = json.loads(result)
        assert isinstance(data["recent_launches"], list)
        assert len(data["recent_launches"]) == 2
        assert data["confidence"] == 0.8

    def test_empty_changelog_returns_low_confidence(self):
        from src.nodes.competitor_tools import fetch_competitor_changelog

        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response([])):
            result = fetch_competitor_changelog.invoke({
                "competitor_name": "Apollo.io",
                "changelog_url": "https://apollo.io/changelog",
            })

        data = json.loads(result)
        assert data["recent_launches"] == []
        assert data["confidence"] == 0.4


# ---------------------------------------------------------------------------
# fetch_producthunt_launches
# ---------------------------------------------------------------------------

class TestFetchProducthuntLaunches:

    def test_returns_launches_list(self):
        from src.nodes.competitor_tools import fetch_producthunt_launches

        ph_data = [
            {
                "product_name": "Apollo.io",
                "tagline": "Find any email",
                "upvotes": 1200,
                "launch_date": "2020-01-15",
                "top_comment_themes": ["great data", "affordable"],
            }
        ]
        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response(ph_data)):
            result = fetch_producthunt_launches.invoke({
                "competitor_name": "Apollo.io",
            })

        data = json.loads(result)
        assert isinstance(data["launches"], list)
        assert data["confidence"] == 0.75
        assert "producthunt_url" in data

    def test_no_results_returns_low_confidence(self):
        from src.nodes.competitor_tools import fetch_producthunt_launches

        with patch("src.nodes.competitor_tools.httpx.post",
                   return_value=_mock_firecrawl_response([])):
            result = fetch_producthunt_launches.invoke({
                "competitor_name": "ObscureCompany",
            })

        data = json.loads(result)
        assert data["launches"] == []
        assert data["confidence"] == 0.3
