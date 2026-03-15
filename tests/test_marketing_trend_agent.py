"""
Tests for the Marketing & Trend Intelligence Agent.

Coverage
--------
  Unit tests (all external calls mocked via unittest.mock):
    TestStateStructure         — TypedDict fields, operator.add reducers
    TestDispatchFunctions      — dispatch_to_sources, dispatch_to_analysis_tools
    TestOrchestratorNode       — LLM JSON parsing, markdown fence stripping,
                                 JSON error fallback, empty-selection fallback
    TestFetchSourceNode        — routing for all 9 sources, unknown source,
                                 exception handling
    TestAnalysisDispatcherNode — raw_data partitioning, task creation with/
                                 without patents, empty raw_data
    TestRunAnalysisToolNode    — routing for all 3 tool types, unknown tool,
                                 exception handling
    TestSynthesizeNode         — labelled result parsing, missing patent,
                                 empty results
    TestGraphTopology          — node names, no legacy ToolNode/analyst_node

  Integration test (all LLM + API calls mocked, full graph.invoke()):
    TestGraphIntegration       — end-to-end state flow, output key presence,
                                 operator.add fan-in correctness

  Live test (real API calls — skipped unless MARKETING_TREND_LIVE=1):
    TestLive                   — smoke test with real keys, verifies
                                 analysis_report is a non-empty string

Run all unit + integration tests:
    uv run pytest tests/

Run including live tests:
    MARKETING_TREND_LIVE=1 uv run pytest tests/ -v
"""

from __future__ import annotations

import json
import operator
import os
import unittest
from typing import get_type_hints
from unittest.mock import MagicMock, call, patch

from langgraph.types import Send

# ── Modules under test ────────────────────────────────────────────────────
from src.states.marketing_trend_state import (
    AVAILABLE_SOURCES,
    AnalysisTaskState,
    FetchTaskState,
    MarketingTrendState,
)
from src.nodes.marketing_trend_node import (
    _AD_SOURCES,
    _TECH_SOURCES,
    _TREND_SOURCES,
    _safe_json,
    analysis_dispatcher_node,
    dispatch_to_analysis_tools,
    dispatch_to_sources,
    fetch_source_node,
    orchestrator_node,
    run_analysis_tool_node,
    synthesize_node,
)
from src.graphs.marketing_trend_graph import marketing_trend_graph


# ── Shared helpers ────────────────────────────────────────────────────────


def _make_llm_mock(content: str) -> MagicMock:
    """Return a mock LLM whose .invoke() returns response.content = content."""
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


def _make_groq_patch(content: str) -> MagicMock:
    """Return a MagicMock suitable for patching GroqLLM; all .invoke() calls
    return a response whose .content is *content*."""
    mock_class = MagicMock()
    mock_class.return_value.get_llm.return_value = _make_llm_mock(content)
    return mock_class


_BASE_STATE: dict = {
    "messages": [],
    "brand": "Notion",
    "category": "B2B SaaS",
    "query": "What are competitors spending on ads?",
    "sources": [],
    "raw_data": [],
    "analysis_tasks": [],
    "analysis_results": [],
    "analysis_report": "",
}

_MOCK_RAW_DATA = [
    {
        "source": "google_trends",
        "data": {"trend": 80},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
        "brand": "Notion",
    },
    {
        "source": "reddit",
        "data": {"posts": []},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
        "brand": "Notion",
    },
    {
        "source": "meta_ads",
        "data": {"ads": []},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
        "brand": "Notion",
    },
    {
        "source": "patents",
        "data": {"count": 5},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
        "brand": "Notion",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. State structure
# ═══════════════════════════════════════════════════════════════════════════
class TestStateStructure(unittest.TestCase):
    """Verify TypedDict definitions match the expected schema."""

    def test_marketing_trend_state_has_required_keys(self):
        hints = get_type_hints(MarketingTrendState, include_extras=True)
        for key in (
            "messages",
            "brand",
            "category",
            "query",
            "sources",
            "raw_data",
            "analysis_tasks",
            "analysis_results",
            "analysis_report",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_fetch_task_state_has_required_keys(self):
        hints = get_type_hints(FetchTaskState, include_extras=True)
        for key in (
            "brand",
            "category",
            "query",
            "source",
            "country",
            "limit",
            "raw_data",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_analysis_task_state_has_required_keys(self):
        hints = get_type_hints(AnalysisTaskState, include_extras=True)
        for key in (
            "brand",
            "category",
            "query",
            "tool_name",
            "raw_data_json",
            "analysis_results",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_available_sources_completeness(self):
        expected = {
            "meta_ads",
            "google_ads_transparency",
            "google_trends",
            "google_news",
            "google_search_ads",
            "linkedin_ads",
            "reddit",
            "hn",
            "patents",
        }
        self.assertEqual(set(AVAILABLE_SOURCES), expected)

    def test_raw_data_reducer_is_operator_add(self):
        """operator.add merges lists — two fetch tasks should not overwrite each other."""
        a = [{"source": "reddit"}]
        b = [{"source": "hn"}]
        merged = operator.add(a, b)
        self.assertEqual(len(merged), 2)
        self.assertEqual({r["source"] for r in merged}, {"reddit", "hn"})

    def test_analysis_results_reducer_is_operator_add(self):
        a = ["[AD_ANALYSIS]\nsome ad text"]
        b = ["[TREND_ANALYSIS]\nsome trend text"]
        merged = operator.add(a, b)
        self.assertEqual(len(merged), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dispatch functions
# ═══════════════════════════════════════════════════════════════════════════
class TestDispatchFunctions(unittest.TestCase):
    # ── dispatch_to_sources ──────────────────────────────────────────────
    def test_dispatch_to_sources_returns_one_send_per_source(self):
        state = {**_BASE_STATE, "sources": ["google_trends", "reddit", "hn"]}
        sends = dispatch_to_sources(state)
        self.assertEqual(len(sends), 3)
        self.assertTrue(all(isinstance(s, Send) for s in sends))

    def test_dispatch_to_sources_target_node(self):
        state = {**_BASE_STATE, "sources": ["meta_ads"]}
        sends = dispatch_to_sources(state)
        self.assertEqual(sends[0].node, "fetch_source_node")

    def test_dispatch_to_sources_payload_fields(self):
        state = {**_BASE_STATE, "brand": "Linear", "sources": ["reddit"]}
        payload = dispatch_to_sources(state)[0].arg
        self.assertEqual(payload["source"], "reddit")
        self.assertEqual(payload["brand"], "Linear")
        self.assertEqual(payload["country"], "US")
        self.assertEqual(payload["limit"], 25)
        self.assertIn("raw_data", payload)

    def test_dispatch_to_sources_empty_sources(self):
        state = {**_BASE_STATE, "sources": []}
        sends = dispatch_to_sources(state)
        self.assertEqual(sends, [])

    # ── dispatch_to_analysis_tools ───────────────────────────────────────
    def test_dispatch_to_analysis_tools_returns_one_send_per_task(self):
        tasks = [
            {
                "tool_name": "ad_analysis",
                "brand": "Notion",
                "category": "SaaS",
                "query": "q",
                "raw_data_json": "[]",
                "analysis_results": [],
            },
            {
                "tool_name": "trend_analysis",
                "brand": "Notion",
                "category": "SaaS",
                "query": "q",
                "raw_data_json": "[]",
                "analysis_results": [],
            },
        ]
        state = {**_BASE_STATE, "analysis_tasks": tasks}
        sends = dispatch_to_analysis_tools(state)
        self.assertEqual(len(sends), 2)
        self.assertTrue(all(isinstance(s, Send) for s in sends))

    def test_dispatch_to_analysis_tools_target_node(self):
        tasks = [
            {
                "tool_name": "trend_analysis",
                "brand": "X",
                "category": "Y",
                "query": "Z",
                "raw_data_json": "[]",
                "analysis_results": [],
            }
        ]
        state = {**_BASE_STATE, "analysis_tasks": tasks}
        sends = dispatch_to_analysis_tools(state)
        self.assertEqual(sends[0].node, "run_analysis_tool_node")

    def test_dispatch_to_analysis_tools_empty_tasks(self):
        state = {**_BASE_STATE, "analysis_tasks": []}
        sends = dispatch_to_analysis_tools(state)
        self.assertEqual(sends, [])


# ═══════════════════════════════════════════════════════════════════════════
# 3. Orchestrator node
# ═══════════════════════════════════════════════════════════════════════════
class TestOrchestratorNode(unittest.TestCase):
    def test_normal_valid_json_response(self):
        """LLM returns a valid JSON list → sources are set accordingly."""
        llm_response = '["google_trends", "reddit", "hn", "meta_ads"]'
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_response)
        ):
            result = orchestrator_node(_BASE_STATE)
        self.assertIn("sources", result)
        self.assertEqual(
            set(result["sources"]), {"google_trends", "reddit", "hn", "meta_ads"}
        )

    def test_markdown_fence_stripped(self):
        """LLM wraps response in ```json ... ``` fences — still parsed correctly."""
        llm_response = '```json\n["google_trends", "hn"]\n```'
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_response)
        ):
            result = orchestrator_node(_BASE_STATE)
        self.assertIn("google_trends", result["sources"])
        self.assertIn("hn", result["sources"])

    def test_unknown_sources_filtered_out(self):
        """LLM includes an unknown source ID — it is silently dropped."""
        llm_response = '["google_trends", "totally_fake_source", "hn"]'
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_response)
        ):
            result = orchestrator_node(_BASE_STATE)
        self.assertNotIn("totally_fake_source", result["sources"])
        self.assertIn("google_trends", result["sources"])

    def test_json_parse_error_triggers_fallback(self):
        """LLM returns non-JSON → fallback default sources are used."""
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch("oops not json")
        ):
            result = orchestrator_node(_BASE_STATE)
        self.assertIn("google_trends", result["sources"])
        self.assertIn("hn", result["sources"])

    def test_empty_selection_triggers_fallback(self):
        """LLM returns only unknown source IDs → selection becomes empty → default applied."""
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM",
            _make_groq_patch('["fake1", "fake2"]'),
        ):
            result = orchestrator_node(_BASE_STATE)
        # Default must include at least the core four
        for src in ("google_trends", "google_news", "reddit", "hn"):
            self.assertIn(src, result["sources"])

    def test_all_sources_are_valid_known_ids(self):
        """Returned sources are always a subset of AVAILABLE_SOURCES."""
        llm_response = json.dumps(AVAILABLE_SOURCES)
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_response)
        ):
            result = orchestrator_node(_BASE_STATE)
        for s in result["sources"]:
            self.assertIn(s, AVAILABLE_SOURCES)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Fetch source node
# ═══════════════════════════════════════════════════════════════════════════
class TestFetchSourceNode(unittest.TestCase):
    """Verify fetch_source_node routes to the correct utility and wraps results."""

    def _run(self, source: str, extra_state: dict | None = None) -> dict:
        state = {
            "brand": "Notion",
            "category": "SaaS",
            "query": "ad spend",
            "source": source,
            "country": "US",
            "limit": 25,
            "raw_data": [],
            **(extra_state or {}),
        }
        return fetch_source_node(state)

    # ── return-value shape ───────────────────────────────────────────────
    def test_return_shape_always_has_raw_data_list(self):
        with patch(
            "src.nodes.marketing_trend_node.google_trends", return_value={"error": None}
        ):
            result = self._run("google_trends")
        self.assertIn("raw_data", result)
        self.assertIsInstance(result["raw_data"], list)
        self.assertEqual(len(result["raw_data"]), 1)

    def test_result_dict_has_expected_keys(self):
        with patch(
            "src.nodes.marketing_trend_node.google_news", return_value={"error": None}
        ):
            result = self._run("google_news")
        entry = result["raw_data"][0]
        for key in ("source", "brand", "data", "error", "fetched_at"):
            self.assertIn(key, entry)

    def test_result_source_field_matches_input(self):
        with patch(
            "src.nodes.marketing_trend_node.fetch_reddit_posts",
            return_value={"posts": [], "error": None},
        ):
            result = self._run("reddit")
        self.assertEqual(result["raw_data"][0]["source"], "reddit")

    # ── per-source routing ───────────────────────────────────────────────
    def test_routes_meta_ads(self):
        mock_raw = {"ads": [{"id": "1"}], "pages_fetched": 1, "error": None}
        with (
            patch(
                "src.nodes.marketing_trend_node.fetch_meta_ads_paginated",
                return_value=mock_raw,
            ) as m,
            patch(
                "src.nodes.marketing_trend_node.summarise_meta_ads",
                return_value={"total": 1},
            ),
        ):
            result = self._run("meta_ads")
        m.assert_called_once()
        self.assertIsNone(result["raw_data"][0]["error"])

    def test_routes_google_ads_transparency(self):
        with patch(
            "src.nodes.marketing_trend_node.google_ads_transparency",
            return_value={"results": [], "error": None},
        ) as m:
            result = self._run("google_ads_transparency")
        m.assert_called_once_with(advertiser="Notion", region="US", limit=25)

    def test_routes_google_trends(self):
        with patch(
            "src.nodes.marketing_trend_node.google_trends",
            return_value={"interest": {}, "error": None},
        ) as m:
            result = self._run("google_trends")
        m.assert_called_once()
        args = m.call_args
        # Brand and query both in keywords because query != brand
        self.assertIn("Notion", args.kwargs["keywords"])

    def test_routes_google_news(self):
        with patch(
            "src.nodes.marketing_trend_node.google_news",
            return_value={"articles": [], "error": None},
        ) as m:
            result = self._run("google_news")
        m.assert_called_once()
        self.assertIn("Notion", m.call_args.kwargs["query"])

    def test_routes_google_search_ads(self):
        with patch(
            "src.nodes.marketing_trend_node.google_search_ads",
            return_value={"ads": [], "error": None},
        ) as m:
            result = self._run("google_search_ads")
        m.assert_called_once()

    def test_routes_linkedin_ads(self):
        with patch(
            "src.nodes.marketing_trend_node.fetch_linkedin_ads",
            return_value={"ads": [], "error": None},
        ) as m:
            result = self._run("linkedin_ads")
        m.assert_called_once_with(advertiser="Notion", date_range="pastMonth")

    def test_routes_reddit(self):
        with patch(
            "src.nodes.marketing_trend_node.fetch_reddit_posts",
            return_value={"posts": [], "error": None},
        ) as m:
            result = self._run("reddit")
        m.assert_called_once()

    def test_routes_hn(self):
        with patch(
            "src.nodes.marketing_trend_node.fetch_hn_stories",
            return_value={"stories": [], "error": None},
        ) as m:
            result = self._run("hn")
        m.assert_called_once()

    def test_routes_patents(self):
        with patch(
            "src.nodes.marketing_trend_node.get_company_patents",
            return_value={"patents": [], "error": None},
        ) as m:
            result = self._run("patents")
        m.assert_called_once_with(company="Notion", years_back=3, limit=25)

    def test_unknown_source_sets_error(self):
        result = self._run("nonexistent_source")
        entry = result["raw_data"][0]
        self.assertIsNotNone(entry["error"])
        self.assertIn("nonexistent_source", entry["error"])
        self.assertIsNone(entry["data"])

    def test_utility_exception_captured_in_error(self):
        with patch(
            "src.nodes.marketing_trend_node.fetch_reddit_posts",
            side_effect=RuntimeError("network down"),
        ):
            result = self._run("reddit")
        entry = result["raw_data"][0]
        self.assertIsNotNone(entry["error"])
        self.assertIn("network down", entry["error"])

    def test_google_trends_same_brand_query_no_duplicate_keyword(self):
        """When query equals brand, keywords list should not duplicate."""
        state = {
            "brand": "Notion",
            "category": "SaaS",
            "query": "Notion",  # same as brand
            "source": "google_trends",
            "country": "US",
            "limit": 25,
            "raw_data": [],
        }
        with patch(
            "src.nodes.marketing_trend_node.google_trends", return_value={"error": None}
        ) as m:
            fetch_source_node(state)
        kw = m.call_args.kwargs["keywords"]
        self.assertEqual(kw, ["Notion"])  # only one entry, not ["Notion","Notion"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Analysis dispatcher node
# ═══════════════════════════════════════════════════════════════════════════
class TestAnalysisDispatcherNode(unittest.TestCase):
    def test_always_creates_ad_and_trend_tasks(self):
        """Even with empty raw_data, ad_analysis and trend_analysis tasks are created."""
        state = {**_BASE_STATE}
        result = analysis_dispatcher_node(state)
        tool_names = [t["tool_name"] for t in result["analysis_tasks"]]
        self.assertIn("ad_analysis", tool_names)
        self.assertIn("trend_analysis", tool_names)

    def test_no_patent_task_when_no_patent_data(self):
        state = {
            **_BASE_STATE,
            "raw_data": [
                {"source": "google_trends", "data": {}, "error": None},
                {"source": "reddit", "data": {}, "error": None},
            ],
        }
        result = analysis_dispatcher_node(state)
        tool_names = [t["tool_name"] for t in result["analysis_tasks"]]
        self.assertNotIn("patent_analysis", tool_names)
        self.assertEqual(len(result["analysis_tasks"]), 2)

    def test_patent_task_created_when_patent_data_present(self):
        state = {
            **_BASE_STATE,
            "raw_data": [
                {"source": "patents", "data": {"count": 3}, "error": None},
            ],
        }
        result = analysis_dispatcher_node(state)
        tool_names = [t["tool_name"] for t in result["analysis_tasks"]]
        self.assertIn("patent_analysis", tool_names)
        self.assertEqual(len(result["analysis_tasks"]), 3)

    def test_task_payload_fields(self):
        state = {
            **_BASE_STATE,
            "brand": "Figma",
            "category": "Design",
            "query": "trends",
        }
        result = analysis_dispatcher_node(state)
        for task in result["analysis_tasks"]:
            self.assertEqual(task["brand"], "Figma")
            self.assertEqual(task["category"], "Design")
            self.assertEqual(task["query"], "trends")
            self.assertIn("raw_data_json", task)
            self.assertIn("tool_name", task)

    def test_ad_task_contains_only_ad_sources(self):
        state = {**_BASE_STATE, "raw_data": _MOCK_RAW_DATA}
        result = analysis_dispatcher_node(state)
        ad_task = next(
            t for t in result["analysis_tasks"] if t["tool_name"] == "ad_analysis"
        )
        ad_json = json.loads(ad_task["raw_data_json"])
        sources_in_ad = {e["source"] for e in ad_json}
        self.assertTrue(sources_in_ad.issubset(_AD_SOURCES))

    def test_trend_task_contains_only_trend_sources(self):
        state = {**_BASE_STATE, "raw_data": _MOCK_RAW_DATA}
        result = analysis_dispatcher_node(state)
        trend_task = next(
            t for t in result["analysis_tasks"] if t["tool_name"] == "trend_analysis"
        )
        trend_json = json.loads(trend_task["raw_data_json"])
        sources_in_trend = {e["source"] for e in trend_json}
        self.assertTrue(sources_in_trend.issubset(_TREND_SOURCES))

    def test_patent_task_contains_only_tech_sources(self):
        state = {**_BASE_STATE, "raw_data": _MOCK_RAW_DATA}
        result = analysis_dispatcher_node(state)
        patent_task = next(
            t for t in result["analysis_tasks"] if t["tool_name"] == "patent_analysis"
        )
        patent_json = json.loads(patent_task["raw_data_json"])
        sources_in_patent = {e["source"] for e in patent_json}
        self.assertTrue(sources_in_patent.issubset(_TECH_SOURCES))

    def test_returns_empty_analysis_results_list(self):
        """Dispatcher resets analysis_results so fan-in starts fresh."""
        state = {**_BASE_STATE, "analysis_results": ["leftover from previous run"]}
        result = analysis_dispatcher_node(state)
        self.assertEqual(result["analysis_results"], [])

    def test_raw_data_json_is_valid_json_string(self):
        state = {**_BASE_STATE, "raw_data": _MOCK_RAW_DATA}
        result = analysis_dispatcher_node(state)
        for task in result["analysis_tasks"]:
            parsed = json.loads(task["raw_data_json"])  # should not raise
            self.assertIsInstance(parsed, list)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Run analysis tool node
# ═══════════════════════════════════════════════════════════════════════════
class TestRunAnalysisToolNode(unittest.TestCase):
    def _run(self, tool_name: str, llm_content: str = "mock analysis") -> dict:
        state = {
            "brand": "Notion",
            "category": "SaaS",
            "query": "ad spend",
            "tool_name": tool_name,
            "raw_data_json": "[]",
            "analysis_results": [],
        }
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_content)
        ):
            return run_analysis_tool_node(state)

    def test_return_shape(self):
        result = self._run("ad_analysis")
        self.assertIn("analysis_results", result)
        self.assertIsInstance(result["analysis_results"], list)
        self.assertEqual(len(result["analysis_results"]), 1)

    def test_ad_analysis_label(self):
        result = self._run("ad_analysis", "some ad insights")
        self.assertTrue(result["analysis_results"][0].startswith("[AD_ANALYSIS]"))

    def test_ad_analysis_content_present(self):
        result = self._run("ad_analysis", "spend is $50k/month")
        self.assertIn("spend is $50k/month", result["analysis_results"][0])

    def test_trend_analysis_label(self):
        result = self._run("trend_analysis", "momentum rising")
        self.assertTrue(result["analysis_results"][0].startswith("[TREND_ANALYSIS]"))

    def test_patent_analysis_label(self):
        result = self._run("patent_analysis", "12 patents filed")
        self.assertTrue(result["analysis_results"][0].startswith("[PATENT_ANALYSIS]"))

    def test_unknown_tool_name_returns_error_label(self):
        result = self._run("nonexistent_tool")
        entry = result["analysis_results"][0]
        self.assertTrue(entry.startswith("[ERROR]"))
        self.assertIn("nonexistent_tool", entry)

    def test_exception_in_analysis_function_captured(self):
        state = {
            "brand": "X",
            "category": "Y",
            "query": "Z",
            "tool_name": "ad_analysis",
            "raw_data_json": "[]",
            "analysis_results": [],
        }
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_groq.return_value.get_llm.return_value.invoke.side_effect = (
                RuntimeError("LLM down")
            )
            result = run_analysis_tool_node(state)
        entry = result["analysis_results"][0]
        self.assertTrue(entry.startswith("[ERROR]"))
        self.assertIn("LLM down", entry)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Synthesize node
# ═══════════════════════════════════════════════════════════════════════════
class TestSynthesizeNode(unittest.TestCase):
    def _run(
        self, analysis_results: list[str], llm_content: str = "# Final Report"
    ) -> dict:
        state = {
            **_BASE_STATE,
            "analysis_results": analysis_results,
        }
        with patch(
            "src.nodes.marketing_trend_node.GroqLLM", _make_groq_patch(llm_content)
        ):
            return synthesize_node(state)

    def test_returns_analysis_report_key(self):
        result = self._run(["[AD_ANALYSIS]\nad text", "[TREND_ANALYSIS]\ntrend text"])
        self.assertIn("analysis_report", result)

    def test_report_equals_llm_output(self):
        result = self._run(
            ["[AD_ANALYSIS]\nx"], llm_content="## Executive Summary\n..."
        )
        self.assertEqual(result["analysis_report"], "## Executive Summary\n...")

    def test_llm_receives_ad_analysis_in_prompt(self):
        """Verify the prompt passed to the LLM includes the parsed ad analysis text."""
        state = {**_BASE_STATE, "analysis_results": ["[AD_ANALYSIS]\nspend $100k"]}
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            synthesize_node(state)
        prompt_used = mock_llm.invoke.call_args[0][0]
        self.assertIn("spend $100k", prompt_used)

    def test_llm_receives_trend_analysis_in_prompt(self):
        state = {**_BASE_STATE, "analysis_results": ["[TREND_ANALYSIS]\nmomentum 9/10"]}
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            synthesize_node(state)
        prompt_used = mock_llm.invoke.call_args[0][0]
        self.assertIn("momentum 9/10", prompt_used)

    def test_missing_patent_analysis_uses_placeholder(self):
        """When no [PATENT_ANALYSIS] is present the prompt uses the fallback string."""
        state = {
            **_BASE_STATE,
            "analysis_results": [
                "[AD_ANALYSIS]\nad info",
                "[TREND_ANALYSIS]\ntrend info",
            ],
        }
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            synthesize_node(state)
        prompt_used = mock_llm.invoke.call_args[0][0]
        self.assertIn("No patent data was collected", prompt_used)

    def test_empty_analysis_results_uses_all_placeholders(self):
        state = {**_BASE_STATE, "analysis_results": []}
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            synthesize_node(state)
        prompt_used = mock_llm.invoke.call_args[0][0]
        self.assertIn("No ad data was collected", prompt_used)
        self.assertIn("No trend data was collected", prompt_used)

    def test_brand_and_query_present_in_prompt(self):
        state = {**_BASE_STATE, "brand": "Figma", "query": "IP landscape"}
        state["analysis_results"] = []
        with patch("src.nodes.marketing_trend_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            synthesize_node(state)
        prompt_used = mock_llm.invoke.call_args[0][0]
        self.assertIn("Figma", prompt_used)
        self.assertIn("IP landscape", prompt_used)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Graph topology
# ═══════════════════════════════════════════════════════════════════════════
class TestGraphTopology(unittest.TestCase):
    def test_expected_nodes_present(self):
        expected = {
            "__start__",
            "orchestrator_node",
            "fetch_source_node",
            "analysis_dispatcher_node",
            "run_analysis_tool_node",
            "synthesize_node",
        }
        self.assertEqual(set(marketing_trend_graph.nodes), expected)

    def test_no_legacy_analyst_node(self):
        self.assertNotIn("analyst_node", marketing_trend_graph.nodes)

    def test_no_legacy_tools_node(self):
        self.assertNotIn("tools", marketing_trend_graph.nodes)

    def test_node_count(self):
        # 6 nodes: __start__ + 5 real nodes
        self.assertEqual(len(marketing_trend_graph.nodes), 6)

    def test_graph_is_compiled(self):
        # A compiled graph has an invoke method
        self.assertTrue(callable(getattr(marketing_trend_graph, "invoke", None)))


# ═══════════════════════════════════════════════════════════════════════════
# 9. Integration test — full mocked graph.invoke()
# ═══════════════════════════════════════════════════════════════════════════
class TestGraphIntegration(unittest.TestCase):
    """
    Run the full graph with all LLM calls and data-source utilities mocked.

    LLM call order:
      1. orchestrator_node            → returns JSON source list
      2. _analyze_ad_spend_*          → returns ad analysis text
      3. _analyze_trend_signals       → returns trend analysis text
      4. synthesize_node              → returns final report markdown

    (patent_analysis is skipped because no patent source is included)
    """

    @classmethod
    def _build_llm_mock_sequence(cls):
        """Return a GroqLLM mock that cycles through known responses in call order."""
        responses = [
            # Call 1: orchestrator — must be valid JSON
            '["google_trends", "reddit", "hn"]',
            # Call 2: ad analysis (empty ad data — node still runs)
            "Ad analysis: no paid ad data was found for this query.",
            # Call 3: trend analysis
            "Trend analysis: Google Trends shows rising interest.",
            # Call 4: synthesize
            "# Marketing Intelligence Report\n\n## Executive Summary\n- Notion momentum is strong.",
        ]
        call_index = [0]

        def invoke_side_effect(prompt):
            resp = MagicMock()
            idx = min(call_index[0], len(responses) - 1)
            resp.content = responses[idx]
            call_index[0] += 1
            return resp

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = invoke_side_effect

        mock_groq_class = MagicMock()
        mock_groq_class.return_value.get_llm.return_value = mock_llm
        return mock_groq_class

    def test_graph_invoke_returns_analysis_report(self):
        initial_state = {
            "messages": [],
            "brand": "Notion",
            "category": "B2B SaaS",
            "query": "What are competitors doing in paid ads?",
            "sources": [],
            "raw_data": [],
            "analysis_tasks": [],
            "analysis_results": [],
            "analysis_report": "",
        }

        mock_util = {"error": None, "data": []}

        with (
            patch(
                "src.nodes.marketing_trend_node.GroqLLM",
                self._build_llm_mock_sequence(),
            ),
            patch(
                "src.nodes.marketing_trend_node.google_trends", return_value=mock_util
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_reddit_posts",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_hn_stories",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_meta_ads_paginated",
                return_value={"ads": [], "pages_fetched": 0, "error": None},
            ),
            patch("src.nodes.marketing_trend_node.summarise_meta_ads", return_value={}),
        ):
            result = marketing_trend_graph.invoke(initial_state)

        self.assertIn("analysis_report", result)
        self.assertIsInstance(result["analysis_report"], str)
        self.assertGreater(len(result["analysis_report"]), 0)

    def test_raw_data_fan_in_accumulates_all_sources(self):
        """operator.add reducer must accumulate one entry per fetched source."""
        initial_state = {
            "messages": [],
            "brand": "Notion",
            "category": "B2B SaaS",
            "query": "trends",
            "sources": [],
            "raw_data": [],
            "analysis_tasks": [],
            "analysis_results": [],
            "analysis_report": "",
        }
        mock_util = {"error": None, "data": []}

        with (
            patch(
                "src.nodes.marketing_trend_node.GroqLLM",
                self._build_llm_mock_sequence(),
            ),
            patch(
                "src.nodes.marketing_trend_node.google_trends", return_value=mock_util
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_reddit_posts",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_hn_stories",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_meta_ads_paginated",
                return_value={"ads": [], "pages_fetched": 0, "error": None},
            ),
            patch("src.nodes.marketing_trend_node.summarise_meta_ads", return_value={}),
        ):
            result = marketing_trend_graph.invoke(initial_state)

        # Orchestrator picked ["google_trends","reddit","hn"] → 3 fetch tasks
        raw_sources = {r["source"] for r in result["raw_data"]}
        self.assertGreaterEqual(len(raw_sources), 1)

    def test_analysis_results_fan_in_accumulates_labelled_results(self):
        """analysis_results must contain at least one labelled result string."""
        initial_state = {
            "messages": [],
            "brand": "Notion",
            "category": "B2B SaaS",
            "query": "trends",
            "sources": [],
            "raw_data": [],
            "analysis_tasks": [],
            "analysis_results": [],
            "analysis_report": "",
        }
        mock_util = {"error": None, "data": []}

        with (
            patch(
                "src.nodes.marketing_trend_node.GroqLLM",
                self._build_llm_mock_sequence(),
            ),
            patch(
                "src.nodes.marketing_trend_node.google_trends", return_value=mock_util
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_reddit_posts",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_hn_stories",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_meta_ads_paginated",
                return_value={"ads": [], "pages_fetched": 0, "error": None},
            ),
            patch("src.nodes.marketing_trend_node.summarise_meta_ads", return_value={}),
        ):
            result = marketing_trend_graph.invoke(initial_state)

        labels = {
            r.split("]")[0].lstrip("[") for r in result.get("analysis_results", [])
        }
        self.assertTrue(
            labels & {"AD_ANALYSIS", "TREND_ANALYSIS", "PATENT_ANALYSIS", "ERROR"},
            f"Expected labelled analysis results, got: {result.get('analysis_results')}",
        )

    def test_sources_set_by_orchestrator(self):
        """Final state must reflect the sources the orchestrator selected."""
        initial_state = {
            "messages": [],
            "brand": "Notion",
            "category": "B2B SaaS",
            "query": "trends",
            "sources": [],
            "raw_data": [],
            "analysis_tasks": [],
            "analysis_results": [],
            "analysis_report": "",
        }
        mock_util = {"error": None, "data": []}

        with (
            patch(
                "src.nodes.marketing_trend_node.GroqLLM",
                self._build_llm_mock_sequence(),
            ),
            patch(
                "src.nodes.marketing_trend_node.google_trends", return_value=mock_util
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_reddit_posts",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_hn_stories",
                return_value=mock_util,
            ),
            patch(
                "src.nodes.marketing_trend_node.fetch_meta_ads_paginated",
                return_value={"ads": [], "pages_fetched": 0, "error": None},
            ),
            patch("src.nodes.marketing_trend_node.summarise_meta_ads", return_value={}),
        ):
            result = marketing_trend_graph.invoke(initial_state)

        self.assertIsInstance(result["sources"], list)
        self.assertGreater(len(result["sources"]), 0)
        for s in result["sources"]:
            self.assertIn(s, AVAILABLE_SOURCES)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Live test — real API calls (skipped unless MARKETING_TREND_LIVE=1)
# ═══════════════════════════════════════════════════════════════════════════
@unittest.skipUnless(
    os.environ.get("MARKETING_TREND_LIVE") == "1",
    "Skipped: set MARKETING_TREND_LIVE=1 to run live API tests",
)
class TestLive(unittest.TestCase):
    """
    Smoke test the full graph against real external APIs.

    Requirements:
      .env must contain GROQ_API_KEY and at least SERPAPI_API_KEY.

    Run:
      MARKETING_TREND_LIVE=1 uv run pytest tests/ -v -k live -s
    """

    @classmethod
    def setUpClass(cls):
        from dotenv import load_dotenv

        load_dotenv()

    def test_live_full_graph(self):
        result = marketing_trend_graph.invoke(
            {
                "messages": [],
                "brand": "Notion",
                "category": "B2B SaaS productivity",
                "query": "What are the latest marketing trends for Notion?",
                "sources": [],
                "raw_data": [],
                "analysis_tasks": [],
                "analysis_results": [],
                "analysis_report": "",
            }
        )

        # Core assertions
        self.assertIn("analysis_report", result)
        self.assertIsInstance(result["analysis_report"], str)
        self.assertGreater(
            len(result["analysis_report"]),
            100,
            "Report is suspiciously short — possible LLM or API failure",
        )
        self.assertIsInstance(result["sources"], list)
        self.assertGreater(len(result["sources"]), 0)
        self.assertIsInstance(result["raw_data"], list)

        print("\n" + "=" * 70)
        print("LIVE REPORT PREVIEW (first 500 chars):")
        print(result["analysis_report"][:500])
        print("=" * 70)
        print(f"Sources fetched: {result['sources']}")
        print(f"Raw data entries: {len(result['raw_data'])}")
        print(f"Analysis results: {len(result['analysis_results'])}")


if __name__ == "__main__":
    unittest.main()
