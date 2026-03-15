"""
tests/test_competitor_node.py

Unit tests for competitor_node.py — planner, fetch, compiler.
LLM calls are MOCKED via LangChain's patch helpers.

Run: pytest tests/test_competitor_node.py -v
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# planner_node
# ---------------------------------------------------------------------------

class TestPlannerNode:

    def _mock_llm_response(self, competitor_list: list) -> MagicMock:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content=json.dumps(competitor_list)
        )
        return mock_llm

    def test_returns_dict_with_competitor_tasks(self):
        from src.nodes.competitor_node import planner_node

        competitors = [
            {"name": "Apollo.io", "website_url": "https://apollo.io",
             "changelog_url": "https://apollo.io/changelog"},
            {"name": "Outreach", "website_url": "https://outreach.io",
             "changelog_url": "https://outreach.io/changelog"},
        ]
        mock_llm = self._mock_llm_response(competitors)

        with patch("src.nodes.competitor_node.GroqLLM") as MockGroq:
            MockGroq.return_value.get_llm.return_value = mock_llm
            result = planner_node({
                "category": "AI SDR",
                "fetched_content": ["Apollo and Outreach are competitors"],
                "messages": [],
            })

        assert isinstance(result, dict)
        assert "competitor_tasks" in result
        assert len(result["competitor_tasks"]) == 2
        assert result["competitor_tasks"][0]["name"] == "Apollo.io"

    def test_handles_invalid_llm_json_gracefully(self):
        from src.nodes.competitor_node import planner_node

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="not json at all")

        with patch("src.nodes.competitor_node.GroqLLM") as MockGroq:
            MockGroq.return_value.get_llm.return_value = mock_llm
            result = planner_node({
                "category": "AI SDR",
                "fetched_content": [],
                "messages": [],
            })

        # Should return empty list, not crash
        assert result == {"competitor_tasks": []}

    def test_handles_empty_fetched_content(self):
        from src.nodes.competitor_node import planner_node

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="[]")

        with patch("src.nodes.competitor_node.GroqLLM") as MockGroq:
            MockGroq.return_value.get_llm.return_value = mock_llm
            result = planner_node({
                "category": "AI SDR",
                "fetched_content": [],
                "messages": [],
            })

        assert result["competitor_tasks"] == []


# ---------------------------------------------------------------------------
# route_to_fetchers
# ---------------------------------------------------------------------------

class TestRouteToFetchers:

    def test_returns_send_per_task(self):
        from src.nodes.competitor_node import route_to_fetchers
        from langgraph.types import Send

        state = {
            "competitor_tasks": [
                {"name": "A", "website_url": "https://a.com",
                 "changelog_url": "", "category": "SaaS"},
                {"name": "B", "website_url": "https://b.com",
                 "changelog_url": "", "category": "SaaS"},
            ]
        }
        sends = route_to_fetchers(state)
        assert len(sends) == 2
        assert all(isinstance(s, Send) for s in sends)
        assert all(s.node == "fetch_competitor" for s in sends)

    def test_empty_tasks_routes_to_compiler(self):
        from src.nodes.competitor_node import route_to_fetchers
        from langgraph.types import Send

        sends = route_to_fetchers({"competitor_tasks": []})
        assert len(sends) == 1
        assert sends[0].node == "compiler"


# ---------------------------------------------------------------------------
# competitor_fetch_node
# ---------------------------------------------------------------------------

class TestCompetitorFetchNode:

    def _make_tool_result(self, data: dict) -> str:
        return json.dumps(data)

    def test_fetches_all_three_tools_concurrently(self):
        from src.nodes.competitor_node import competitor_fetch_node

        website_result = json.dumps({"competitor": "Apollo.io", "data": {}, "confidence": 0.85})
        changelog_result = json.dumps({"competitor": "Apollo.io", "recent_launches": [], "confidence": 0.4})
        ph_result = json.dumps({"competitor": "Apollo.io", "launches": [], "confidence": 0.3})

        with patch("src.nodes.competitor_node.fetch_competitor_website") as mock_w, \
             patch("src.nodes.competitor_node.fetch_competitor_changelog") as mock_c, \
             patch("src.nodes.competitor_node.fetch_producthunt_launches") as mock_ph:

            mock_w.invoke.return_value = website_result
            mock_c.invoke.return_value = changelog_result
            mock_ph.invoke.return_value = ph_result

            result = competitor_fetch_node({
                "name": "Apollo.io",
                "website_url": "https://apollo.io",
                "changelog_url": "https://apollo.io/changelog",
                "category": "AI SDR",
            })

        assert "competitor_results" in result
        assert len(result["competitor_results"]) == 1
        cr = result["competitor_results"][0]
        assert cr["name"] == "Apollo.io"
        assert cr["website_data"] is not None
        assert cr["changelog_data"] is not None
        assert cr["producthunt_data"] is not None

    def test_continues_if_one_tool_fails(self):
        from src.nodes.competitor_node import competitor_fetch_node

        website_result = json.dumps({"competitor": "Apollo.io", "data": {}, "confidence": 0.85})

        with patch("src.nodes.competitor_node.fetch_competitor_website") as mock_w, \
             patch("src.nodes.competitor_node.fetch_competitor_changelog") as mock_c, \
             patch("src.nodes.competitor_node.fetch_producthunt_launches") as mock_ph:

            mock_w.invoke.return_value = website_result
            mock_c.invoke.side_effect = Exception("Timeout")
            mock_ph.invoke.side_effect = Exception("Rate limit")

            # Should NOT raise — graceful degradation
            result = competitor_fetch_node({
                "name": "Apollo.io",
                "website_url": "https://apollo.io",
                "changelog_url": "",
                "category": "AI SDR",
            })

        assert "competitor_results" in result


# ---------------------------------------------------------------------------
# compiler_node
# ---------------------------------------------------------------------------

class TestCompilerNode:

    def _sample_competitor_results(self) -> list:
        return [
            {
                "name": "Apollo.io",
                "website_url": "https://apollo.io",
                "website_data": {
                    "data": {
                        "company_tagline": "AI sales platform",
                        "features": ["email", "CRM"],
                        "pricing_tier": "freemium",
                    },
                    "confidence": 0.85,
                },
                "changelog_data": {"recent_launches": [], "confidence": 0.4},
                "producthunt_data": {"launches": [], "confidence": 0.3},
            }
        ]

    def test_produces_valid_competitive_payload(self):
        from src.nodes.competitor_node import compiler_node

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content=json.dumps({
            "competitors": [
                {
                    "name": "Apollo.io",
                    "website": "https://apollo.io",
                    "tagline": "AI sales platform",
                    "features": {
                        "email_personalization": {"present": True, "confidence": 0.9}
                    },
                    "last_updated": "2026-03-15T00:00:00",
                    "recent_launches": [],
                    "pricing_tier": "freemium",
                    "sources": [],
                }
            ],
            "feature_columns": ["email_personalization"],
            "category_summary": "AI SDR tools are consolidating around email.",
            "standard_features": ["email_personalization"],
            "differentiator_features": [],
            "missing_features": ["inbound_qualification"],
            "overall_confidence": 0.75,
        }))

        with patch("src.nodes.competitor_node.GroqLLM") as MockGroq:
            MockGroq.return_value.get_llm.return_value = mock_llm
            result = compiler_node({
                "competitor_results": self._sample_competitor_results(),
            })

        assert "structured_output" in result
        assert "analysis_result" in result
        so = result["structured_output"]
        assert len(so["competitors"]) == 1
        assert so["overall_confidence"] == 0.75
        assert "email_personalization" in so["feature_columns"]

    def test_empty_results_returns_fallback_payload(self):
        from src.nodes.competitor_node import compiler_node

        result = compiler_node({"competitor_results": []})

        so = result["structured_output"]
        assert so["competitors"] == []
        assert so["overall_confidence"] == 0.1
        assert "No competitor data" in result["analysis_result"]

    def test_compiler_handles_llm_json_parse_failure(self):
        from src.nodes.competitor_node import compiler_node

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="definitely not json")

        with patch("src.nodes.competitor_node.GroqLLM") as MockGroq:
            MockGroq.return_value.get_llm.return_value = mock_llm
            result = compiler_node({
                "competitor_results": self._sample_competitor_results(),
            })

        # Should degrade gracefully
        assert result["structured_output"]["overall_confidence"] == 0.1
        assert "failed" in result["analysis_result"].lower()
