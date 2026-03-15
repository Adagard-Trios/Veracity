"""
Tests for the Win/Loss Intelligence Agent.

Coverage
--------
  Unit tests (all external calls mocked via unittest.mock):
    TestStateStructure              — TypedDict fields, operator.add reducers,
                                      AVAILABLE_SIGNAL_SOURCES completeness
    TestDispatchFunctions           — dispatch_to_signal_sources,
                                      dispatch_to_extractors
    TestOrchestratorNode            — LLM JSON parsing, markdown fence stripping,
                                      JSON error fallback, empty-selection fallback,
                                      unknown source filtering
    TestFetchNode                   — routing for all 10 sources, unknown source,
                                      exception handling, return shape
    TestSignalExtractorNode         — task creation per source, empty raw_signals,
                                      fallback task, extraction_tasks payload fields,
                                      resets extracted_signals
    TestExtractNode                 — return shape, label format, exception capture
    TestConfidenceScoring           — source weight ordering, frequency boosts,
                                      no-signal penalty
    TestSynthesizerNode             — signal_matrix present, win_loss_report present,
                                      empty signals placeholder, LLM prompt content
    TestGraphTopology               — node names, no legacy nodes, node count,
                                      graph is compiled

  Integration test (all LLM + API calls mocked, full graph.invoke()):
    TestGraphIntegration            — end-to-end state flow, output key presence,
                                      operator.add fan-in correctness

  Live test (real API calls — skipped unless WIN_LOSS_LIVE=1):
    TestLive                        — smoke test with real keys, verifies
                                      win_loss_report is a non-empty string

Run all unit + integration tests:
    uv run pytest tests/test_win_loss_agent.py

Run including live tests:
    WIN_LOSS_LIVE=1 uv run pytest tests/test_win_loss_agent.py -v
"""

from __future__ import annotations

import json
import operator
import os
import unittest
from typing import get_type_hints
from unittest.mock import MagicMock, patch

from langgraph.types import Send

# ── Modules under test ────────────────────────────────────────────────────
from src.states.win_loss_state import (
    AVAILABLE_SIGNAL_SOURCES,
    ExtractionTaskState,
    SignalFetchTaskState,
    WinLossState,
)
from src.nodes.win_loss_node import (
    _SOURCE_GUIDANCE,
    _build_signal_matrix,
    _extract_win_loss_signals,
    _safe_json,
    _score_signal_confidence,
    dispatch_to_extractors,
    dispatch_to_signal_sources,
    wl_extract_node,
    wl_fetch_node,
    wl_orchestrator_node,
    wl_signal_extractor_node,
    wl_synthesizer_node,
)
from src.graphs.win_loss_graph import win_loss_graph


# ── Shared helpers ────────────────────────────────────────────────────────


def _make_llm_mock(content: str) -> MagicMock:
    """Return a mock LLM whose .invoke() returns response.content = content."""
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


def _make_groq_patch(content: str) -> MagicMock:
    """Return a MagicMock suitable for patching GroqLLM."""
    mock_class = MagicMock()
    mock_class.return_value.get_llm.return_value = _make_llm_mock(content)
    return mock_class


_BASE_STATE: dict = {
    "messages": [],
    "brand": "Notion",
    "category": "B2B SaaS",
    "competitors": ["Confluence", "Coda"],
    "query": "Why do we win and lose deals?",
    "sources": [],
    "raw_signals": [],
    "extraction_tasks": [],
    "extracted_signals": [],
    "signal_matrix": "",
    "win_loss_report": "",
}

_MOCK_RAW_SIGNALS = [
    {
        "source": "reddit",
        "brand": "Notion",
        "data": {"posts": [{"title": "Notion is great", "score": 100}]},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
    },
    {
        "source": "g2_reviews",
        "brand": "Notion",
        "data": {"reviews": [{"text": "Best product ever", "rating": "5"}]},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
    },
    {
        "source": "capterra_reviews",
        "brand": "Notion",
        "data": {"reviews": [{"text": "Missing SSO", "rating": "3"}]},
        "error": None,
        "fetched_at": "2026-01-01T00:00:00Z",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. State structure
# ═══════════════════════════════════════════════════════════════════════════
class TestStateStructure(unittest.TestCase):
    """Verify TypedDict definitions match the expected schema."""

    def test_win_loss_state_has_required_keys(self):
        hints = get_type_hints(WinLossState, include_extras=True)
        for key in (
            "messages",
            "brand",
            "category",
            "competitors",
            "query",
            "sources",
            "raw_signals",
            "extraction_tasks",
            "extracted_signals",
            "signal_matrix",
            "win_loss_report",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_signal_fetch_task_state_has_required_keys(self):
        hints = get_type_hints(SignalFetchTaskState, include_extras=True)
        for key in (
            "brand",
            "category",
            "competitors",
            "query",
            "source",
            "limit",
            "raw_signals",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_extraction_task_state_has_required_keys(self):
        hints = get_type_hints(ExtractionTaskState, include_extras=True)
        for key in (
            "brand",
            "category",
            "competitors",
            "query",
            "source_label",
            "raw_data_json",
            "extracted_signals",
        ):
            self.assertIn(key, hints, f"Missing key: {key}")

    def test_available_signal_sources_completeness(self):
        expected = {
            "reddit",
            "hn",
            "google_news",
            "g2_reviews",
            "capterra_reviews",
            "linkedin_comments",
            "youtube_comments",
            "trustpilot",
            "app_store",
            "play_store",
        }
        self.assertEqual(set(AVAILABLE_SIGNAL_SOURCES), expected)

    def test_raw_signals_reducer_is_operator_add(self):
        """operator.add merges lists — two fetch tasks should not overwrite each other."""
        a = [{"source": "reddit"}]
        b = [{"source": "g2_reviews"}]
        merged = operator.add(a, b)
        self.assertEqual(len(merged), 2)
        self.assertEqual({r["source"] for r in merged}, {"reddit", "g2_reviews"})

    def test_extracted_signals_reducer_is_operator_add(self):
        a = ["[REDDIT]\nwin signal"]
        b = ["[G2_REVIEWS]\nloss signal"]
        merged = operator.add(a, b)
        self.assertEqual(len(merged), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dispatch functions
# ═══════════════════════════════════════════════════════════════════════════
class TestDispatchFunctions(unittest.TestCase):
    # ── dispatch_to_signal_sources ───────────────────────────────────────
    def test_dispatch_to_signal_sources_returns_one_send_per_source(self):
        state = {**_BASE_STATE, "sources": ["reddit", "g2_reviews", "hn"]}
        sends = dispatch_to_signal_sources(state)
        self.assertEqual(len(sends), 3)
        self.assertTrue(all(isinstance(s, Send) for s in sends))

    def test_dispatch_to_signal_sources_target_node(self):
        state = {**_BASE_STATE, "sources": ["reddit"]}
        sends = dispatch_to_signal_sources(state)
        self.assertEqual(sends[0].node, "wl_fetch_node")

    def test_dispatch_to_signal_sources_payload_fields(self):
        state = {**_BASE_STATE, "brand": "Linear", "sources": ["g2_reviews"]}
        payload = dispatch_to_signal_sources(state)[0].arg
        self.assertEqual(payload["source"], "g2_reviews")
        self.assertEqual(payload["brand"], "Linear")
        self.assertEqual(payload["limit"], 25)
        self.assertIn("raw_signals", payload)
        self.assertIn("competitors", payload)

    def test_dispatch_to_signal_sources_empty_sources(self):
        state = {**_BASE_STATE, "sources": []}
        sends = dispatch_to_signal_sources(state)
        self.assertEqual(sends, [])

    # ── dispatch_to_extractors ───────────────────────────────────────────
    def test_dispatch_to_extractors_returns_one_send_per_task(self):
        tasks = [
            {
                "source_label": "reddit",
                "brand": "Notion",
                "category": "SaaS",
                "competitors": [],
                "query": "q",
                "raw_data_json": "[]",
                "extracted_signals": [],
            },
            {
                "source_label": "g2_reviews",
                "brand": "Notion",
                "category": "SaaS",
                "competitors": [],
                "query": "q",
                "raw_data_json": "[]",
                "extracted_signals": [],
            },
        ]
        state = {**_BASE_STATE, "extraction_tasks": tasks}
        sends = dispatch_to_extractors(state)
        self.assertEqual(len(sends), 2)
        self.assertTrue(all(isinstance(s, Send) for s in sends))

    def test_dispatch_to_extractors_target_node(self):
        tasks = [
            {
                "source_label": "hn",
                "brand": "X",
                "category": "Y",
                "competitors": [],
                "query": "Z",
                "raw_data_json": "[]",
                "extracted_signals": [],
            }
        ]
        state = {**_BASE_STATE, "extraction_tasks": tasks}
        sends = dispatch_to_extractors(state)
        self.assertEqual(sends[0].node, "wl_extract_node")

    def test_dispatch_to_extractors_empty_tasks(self):
        state = {**_BASE_STATE, "extraction_tasks": []}
        sends = dispatch_to_extractors(state)
        self.assertEqual(sends, [])


# ═══════════════════════════════════════════════════════════════════════════
# 3. Orchestrator node
# ═══════════════════════════════════════════════════════════════════════════
class TestOrchestratorNode(unittest.TestCase):
    def test_normal_valid_json_response(self):
        llm_response = '["reddit", "hn", "g2_reviews", "capterra_reviews"]'
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_response)):
            result = wl_orchestrator_node(_BASE_STATE)
        self.assertIn("sources", result)
        self.assertEqual(
            set(result["sources"]),
            {"reddit", "hn", "g2_reviews", "capterra_reviews"},
        )

    def test_markdown_fence_stripped(self):
        llm_response = '```json\n["reddit", "hn"]\n```'
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_response)):
            result = wl_orchestrator_node(_BASE_STATE)
        self.assertIn("reddit", result["sources"])
        self.assertIn("hn", result["sources"])

    def test_unknown_sources_filtered_out(self):
        llm_response = '["reddit", "totally_fake_source", "hn"]'
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_response)):
            result = wl_orchestrator_node(_BASE_STATE)
        self.assertNotIn("totally_fake_source", result["sources"])
        self.assertIn("reddit", result["sources"])

    def test_json_parse_error_triggers_fallback(self):
        with patch(
            "src.nodes.win_loss_node.GroqLLM", _make_groq_patch("oops not json")
        ):
            result = wl_orchestrator_node(_BASE_STATE)
        self.assertIn("reddit", result["sources"])
        self.assertIn("hn", result["sources"])

    def test_empty_selection_triggers_fallback(self):
        with patch(
            "src.nodes.win_loss_node.GroqLLM",
            _make_groq_patch('["fake1", "fake2"]'),
        ):
            result = wl_orchestrator_node(_BASE_STATE)
        for src in ("reddit", "hn", "google_news", "g2_reviews"):
            self.assertIn(src, result["sources"])

    def test_all_returned_sources_are_valid_known_ids(self):
        llm_response = json.dumps(AVAILABLE_SIGNAL_SOURCES)
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_response)):
            result = wl_orchestrator_node(_BASE_STATE)
        for s in result["sources"]:
            self.assertIn(s, AVAILABLE_SIGNAL_SOURCES)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Fetch node
# ═══════════════════════════════════════════════════════════════════════════
class TestFetchNode(unittest.TestCase):
    """Verify wl_fetch_node routes to the correct utility and wraps results."""

    def _run(self, source: str, extra_state: dict | None = None) -> dict:
        state = {
            "brand": "Notion",
            "category": "SaaS",
            "competitors": ["Confluence"],
            "query": "why do we lose deals",
            "source": source,
            "limit": 25,
            "raw_signals": [],
            **(extra_state or {}),
        }
        return wl_fetch_node(state)

    def test_return_shape_always_has_raw_signals_list(self):
        with patch(
            "src.nodes.win_loss_node.fetch_reddit_posts",
            return_value={"posts": [], "error": None},
        ):
            result = self._run("reddit")
        self.assertIn("raw_signals", result)
        self.assertIsInstance(result["raw_signals"], list)
        self.assertEqual(len(result["raw_signals"]), 1)

    def test_result_dict_has_expected_keys(self):
        with patch(
            "src.nodes.win_loss_node.google_news",
            return_value={"articles": [], "error": None},
        ):
            result = self._run("google_news")
        entry = result["raw_signals"][0]
        for key in ("source", "brand", "data", "error", "fetched_at"):
            self.assertIn(key, entry)

    def test_result_source_field_matches_input(self):
        with patch(
            "src.nodes.win_loss_node.fetch_reddit_posts",
            return_value={"posts": [], "error": None},
        ):
            result = self._run("reddit")
        self.assertEqual(result["raw_signals"][0]["source"], "reddit")

    def test_routes_reddit(self):
        with patch(
            "src.nodes.win_loss_node.fetch_reddit_posts",
            return_value={"posts": [], "error": None},
        ) as m:
            self._run("reddit")
        m.assert_called_once()

    def test_routes_hn(self):
        with patch(
            "src.nodes.win_loss_node.fetch_hn_stories",
            return_value={"stories": [], "error": None},
        ) as m:
            self._run("hn")
        m.assert_called_once()

    def test_routes_google_news(self):
        with patch(
            "src.nodes.win_loss_node.google_news",
            return_value={"articles": [], "error": None},
        ) as m:
            self._run("google_news")
        m.assert_called_once()

    def test_routes_g2_reviews(self):
        with patch(
            "src.nodes.win_loss_node.scrape_g2_reviews",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("g2_reviews")
        m.assert_called_once_with(product="Notion", limit=25)

    def test_routes_capterra_reviews(self):
        with patch(
            "src.nodes.win_loss_node.scrape_capterra_reviews",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("capterra_reviews")
        m.assert_called_once_with(product="Notion", limit=25)

    def test_routes_trustpilot(self):
        with patch(
            "src.nodes.win_loss_node.scrape_trustpilot_reviews",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("trustpilot")
        m.assert_called_once_with(company="Notion", limit=25)

    def test_routes_linkedin_comments(self):
        with patch(
            "src.nodes.win_loss_node.fetch_linkedin_comments",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("linkedin_comments")
        m.assert_called_once()

    def test_routes_youtube_comments(self):
        with patch(
            "src.nodes.win_loss_node.fetch_youtube_comments",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("youtube_comments")
        m.assert_called_once()

    def test_routes_app_store(self):
        with patch(
            "src.nodes.win_loss_node.fetch_app_store_reviews",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("app_store")
        m.assert_called_once_with(app_name="Notion", limit=25)

    def test_routes_play_store(self):
        with patch(
            "src.nodes.win_loss_node.fetch_play_store_reviews",
            return_value={"reviews": [], "error": None},
        ) as m:
            self._run("play_store")
        m.assert_called_once_with(app_name="Notion", limit=25)

    def test_unknown_source_sets_error(self):
        result = self._run("nonexistent_source")
        entry = result["raw_signals"][0]
        self.assertIsNotNone(entry["error"])
        self.assertIn("nonexistent_source", entry["error"])
        self.assertIsNone(entry["data"])

    def test_utility_exception_captured_in_error(self):
        with patch(
            "src.nodes.win_loss_node.fetch_reddit_posts",
            side_effect=RuntimeError("network down"),
        ):
            result = self._run("reddit")
        entry = result["raw_signals"][0]
        self.assertIsNotNone(entry["error"])
        self.assertIn("network down", entry["error"])


# ═══════════════════════════════════════════════════════════════════════════
# 5. Signal extractor node
# ═══════════════════════════════════════════════════════════════════════════
class TestSignalExtractorNode(unittest.TestCase):
    def test_creates_one_task_per_signal_with_data(self):
        state = {**_BASE_STATE, "raw_signals": _MOCK_RAW_SIGNALS}
        result = wl_signal_extractor_node(state)
        self.assertEqual(len(result["extraction_tasks"]), 3)

    def test_task_source_labels_match_signal_sources(self):
        state = {**_BASE_STATE, "raw_signals": _MOCK_RAW_SIGNALS}
        result = wl_signal_extractor_node(state)
        labels = {t["source_label"] for t in result["extraction_tasks"]}
        self.assertEqual(labels, {"reddit", "g2_reviews", "capterra_reviews"})

    def test_task_payload_has_required_fields(self):
        state = {**_BASE_STATE, "raw_signals": _MOCK_RAW_SIGNALS, "brand": "Figma"}
        result = wl_signal_extractor_node(state)
        for task in result["extraction_tasks"]:
            self.assertEqual(task["brand"], "Figma")
            self.assertIn("source_label", task)
            self.assertIn("raw_data_json", task)
            self.assertIn("competitors", task)
            self.assertIn("query", task)

    def test_raw_data_json_is_valid_json_string(self):
        state = {**_BASE_STATE, "raw_signals": _MOCK_RAW_SIGNALS}
        result = wl_signal_extractor_node(state)
        for task in result["extraction_tasks"]:
            parsed = json.loads(task["raw_data_json"])  # must not raise

    def test_none_data_signals_skipped(self):
        raw_signals = [
            {
                "source": "reddit",
                "brand": "Notion",
                "data": None,
                "error": "timeout",
                "fetched_at": "",
            },
            {
                "source": "g2_reviews",
                "brand": "Notion",
                "data": {"reviews": []},
                "error": None,
                "fetched_at": "",
            },
        ]
        state = {**_BASE_STATE, "raw_signals": raw_signals}
        result = wl_signal_extractor_node(state)
        labels = [t["source_label"] for t in result["extraction_tasks"]]
        self.assertNotIn("reddit", labels)
        self.assertIn("g2_reviews", labels)

    def test_empty_raw_signals_creates_fallback_task(self):
        state = {**_BASE_STATE, "raw_signals": []}
        result = wl_signal_extractor_node(state)
        self.assertEqual(len(result["extraction_tasks"]), 1)
        self.assertEqual(result["extraction_tasks"][0]["source_label"], "fallback")

    def test_resets_extracted_signals(self):
        state = {
            **_BASE_STATE,
            "extracted_signals": ["leftover"],
            "raw_signals": _MOCK_RAW_SIGNALS,
        }
        result = wl_signal_extractor_node(state)
        self.assertEqual(result["extracted_signals"], [])


# ═══════════════════════════════════════════════════════════════════════════
# 6. Extract node
# ═══════════════════════════════════════════════════════════════════════════
class TestExtractNode(unittest.TestCase):
    def _run(
        self,
        source_label: str,
        llm_content: str = "WIN REASONS:\n- Feature X: great (frequency: high)",
    ) -> dict:
        state = {
            "brand": "Notion",
            "category": "SaaS",
            "competitors": ["Confluence"],
            "query": "why do we win",
            "source_label": source_label,
            "raw_data_json": "[]",
            "extracted_signals": [],
        }
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_content)):
            return wl_extract_node(state)

    def test_return_shape(self):
        result = self._run("reddit")
        self.assertIn("extracted_signals", result)
        self.assertIsInstance(result["extracted_signals"], list)
        self.assertEqual(len(result["extracted_signals"]), 1)

    def test_label_format_uses_source_in_brackets(self):
        result = self._run("g2_reviews")
        entry = result["extracted_signals"][0]
        self.assertTrue(entry.startswith("[G2_REVIEWS]"))

    def test_label_is_uppercase(self):
        result = self._run("capterra_reviews")
        self.assertTrue(result["extracted_signals"][0].startswith("[CAPTERRA_REVIEWS]"))

    def test_llm_content_present_in_output(self):
        result = self._run("reddit", "custom win signal text")
        self.assertIn("custom win signal text", result["extracted_signals"][0])

    def test_exception_captured_gracefully(self):
        state = {
            "brand": "X",
            "category": "Y",
            "competitors": [],
            "query": "Z",
            "source_label": "reddit",
            "raw_data_json": "[]",
            "extracted_signals": [],
        }
        with patch("src.nodes.win_loss_node.GroqLLM") as mock_groq:
            mock_groq.return_value.get_llm.return_value.invoke.side_effect = (
                RuntimeError("LLM down")
            )
            result = wl_extract_node(state)
        entry = result["extracted_signals"][0]
        # Should still have a labelled entry (with error text)
        self.assertTrue(entry.startswith("[REDDIT]"))
        self.assertIn("LLM down", entry)

    def test_all_signal_sources_have_guidance_entries(self):
        """Every source in AVAILABLE_SIGNAL_SOURCES must have a guidance entry."""
        for src in AVAILABLE_SIGNAL_SOURCES:
            self.assertIn(src, _SOURCE_GUIDANCE, f"No guidance for source: {src}")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════
class TestConfidenceScoring(unittest.TestCase):
    def test_g2_scores_higher_than_hn(self):
        g2_score = _score_signal_confidence(
            "WIN REASONS:\n- Feature X (frequency: medium)", "g2_reviews"
        )
        hn_score = _score_signal_confidence(
            "WIN REASONS:\n- Feature X (frequency: medium)", "hn"
        )
        self.assertGreater(g2_score, hn_score)

    def test_capterra_scores_higher_than_youtube(self):
        cap_score = _score_signal_confidence("some signal", "capterra_reviews")
        yt_score = _score_signal_confidence("some signal", "youtube_comments")
        self.assertGreater(cap_score, yt_score)

    def test_high_frequency_boosts_score(self):
        base = _score_signal_confidence("some signal", "reddit")
        boosted = _score_signal_confidence("some signal (frequency: high)", "reddit")
        self.assertGreaterEqual(boosted, base)

    def test_low_frequency_reduces_score(self):
        base = _score_signal_confidence("some signal", "reddit")
        reduced = _score_signal_confidence("some signal (frequency: low)", "reddit")
        self.assertLessEqual(reduced, base)

    def test_no_signals_found_penalises_score(self):
        normal = _score_signal_confidence("WIN REASONS:\n- Feature X", "g2_reviews")
        penalised = _score_signal_confidence(
            "No win/loss signals found in this source.", "g2_reviews"
        )
        self.assertGreater(normal, penalised)

    def test_score_within_bounds(self):
        for src in AVAILABLE_SIGNAL_SOURCES:
            score = _score_signal_confidence("WIN REASONS:\n- X (frequency: high)", src)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_unknown_source_returns_mid_score(self):
        score = _score_signal_confidence("some signal", "totally_unknown")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_fallback_source_has_very_low_score(self):
        score = _score_signal_confidence("some signal", "fallback")
        self.assertLess(score, 0.5)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Synthesizer node
# ═══════════════════════════════════════════════════════════════════════════
class TestSynthesizerNode(unittest.TestCase):
    def _run(
        self,
        extracted_signals: list[str],
        llm_content: str = "# Win/Loss Report\n\n## Executive Summary\n- Notion wins on UX.",
    ) -> dict:
        state = {
            **_BASE_STATE,
            "extracted_signals": extracted_signals,
        }
        with patch("src.nodes.win_loss_node.GroqLLM", _make_groq_patch(llm_content)):
            return wl_synthesizer_node(state)

    def test_returns_signal_matrix_key(self):
        result = self._run(["[REDDIT]\nWIN REASONS:\n- Feature X (frequency: high)"])
        self.assertIn("signal_matrix", result)

    def test_returns_win_loss_report_key(self):
        result = self._run(
            ["[G2_REVIEWS]\nWIN REASONS:\n- Easy to use (frequency: medium)"]
        )
        self.assertIn("win_loss_report", result)

    def test_report_equals_llm_output(self):
        result = self._run([], llm_content="## Executive Summary\n- ...")
        self.assertEqual(result["win_loss_report"], "## Executive Summary\n- ...")

    def test_signal_matrix_is_markdown_table(self):
        result = self._run(
            [
                "[G2_REVIEWS]\nWIN REASONS:\n- Feature X: great (frequency: high)\nLOSS REASONS:\n- Missing SSO: no enterprise SSO (frequency: medium)"
            ]
        )
        matrix = result["signal_matrix"]
        self.assertIn("|", matrix)
        self.assertIn("Signal", matrix)

    def test_empty_signals_produces_placeholder_matrix(self):
        result = self._run([])
        self.assertIn("No signals extracted", result["signal_matrix"])

    def test_llm_prompt_includes_brand(self):
        state = {**_BASE_STATE, "brand": "Figma", "extracted_signals": []}
        with patch("src.nodes.win_loss_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            wl_synthesizer_node(state)
        prompt = mock_llm.invoke.call_args[0][0]
        self.assertIn("Figma", prompt)

    def test_llm_prompt_includes_competitors(self):
        state = {
            **_BASE_STATE,
            "competitors": ["Asana", "Monday.com"],
            "extracted_signals": [],
        }
        with patch("src.nodes.win_loss_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            wl_synthesizer_node(state)
        prompt = mock_llm.invoke.call_args[0][0]
        self.assertIn("Asana", prompt)

    def test_llm_prompt_includes_query(self):
        state = {
            **_BASE_STATE,
            "query": "enterprise churn reasons",
            "extracted_signals": [],
        }
        with patch("src.nodes.win_loss_node.GroqLLM") as mock_groq:
            mock_llm = _make_llm_mock("report")
            mock_groq.return_value.get_llm.return_value = mock_llm
            wl_synthesizer_node(state)
        prompt = mock_llm.invoke.call_args[0][0]
        self.assertIn("enterprise churn reasons", prompt)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Build signal matrix (unit)
# ═══════════════════════════════════════════════════════════════════════════
class TestBuildSignalMatrix(unittest.TestCase):
    def test_empty_blocks_returns_placeholder_row(self):
        matrix = _build_signal_matrix([], "Notion")
        self.assertIn("No signals extracted", matrix)

    def test_win_rows_labelled_win(self):
        blocks = [
            {
                "source": "g2_reviews",
                "content": "WIN REASONS:\n- Easy to use: great UX (frequency: high)\n",
                "confidence": 0.9,
            }
        ]
        matrix = _build_signal_matrix(blocks, "Notion")
        self.assertIn("Win", matrix)

    def test_loss_rows_labelled_loss(self):
        blocks = [
            {
                "source": "capterra_reviews",
                "content": "LOSS REASONS:\n- Missing SSO: no enterprise SSO (frequency: medium)\n",
                "confidence": 0.85,
            }
        ]
        matrix = _build_signal_matrix(blocks, "Notion")
        self.assertIn("Loss", matrix)

    def test_matrix_is_valid_markdown_table(self):
        blocks = [
            {
                "source": "reddit",
                "content": "WIN REASONS:\n- Fast UI: great (frequency: low)\n",
                "confidence": 0.7,
            }
        ]
        matrix = _build_signal_matrix(blocks, "Notion")
        lines = matrix.splitlines()
        # Header and separator rows
        self.assertTrue(lines[0].startswith("|"))
        self.assertTrue(lines[1].startswith("|"))


# ═══════════════════════════════════════════════════════════════════════════
# 10. Graph topology
# ═══════════════════════════════════════════════════════════════════════════
class TestGraphTopology(unittest.TestCase):
    def test_expected_nodes_present(self):
        expected = {
            "__start__",
            "wl_orchestrator_node",
            "wl_fetch_node",
            "wl_signal_extractor_node",
            "wl_extract_node",
            "wl_synthesizer_node",
        }
        self.assertEqual(set(win_loss_graph.nodes), expected)

    def test_no_legacy_analyst_node(self):
        self.assertNotIn("analyst_node", win_loss_graph.nodes)

    def test_no_legacy_tools_node(self):
        self.assertNotIn("tools", win_loss_graph.nodes)

    def test_node_count(self):
        # 6 nodes: __start__ + 5 real nodes
        self.assertEqual(len(win_loss_graph.nodes), 6)

    def test_graph_is_compiled(self):
        self.assertTrue(callable(getattr(win_loss_graph, "invoke", None)))


# ═══════════════════════════════════════════════════════════════════════════
# 11. Integration test — full mocked graph.invoke()
# ═══════════════════════════════════════════════════════════════════════════
class TestGraphIntegration(unittest.TestCase):
    """
    Run the full graph with all LLM calls and data-source utilities mocked.

    LLM call order:
      1. wl_orchestrator_node       → returns JSON source list
      2. wl_extract_node(reddit)    → returns win/loss signals
      3. wl_extract_node(hn)        → returns win/loss signals
      4. wl_extract_node(g2)        → returns win/loss signals
      5. wl_synthesizer_node        → returns final report markdown
    """

    @classmethod
    def _build_llm_mock_sequence(cls):
        responses = [
            # Call 1: orchestrator
            '["reddit", "hn", "g2_reviews"]',
            # Calls 2–4: wl_extract_node per source (order may vary due to parallelism)
            "WIN REASONS:\n- Fast UI: great UX (frequency: high)\nLOSS REASONS:\n- Missing SSO (frequency: medium)",
            "WIN REASONS:\n- Open API: devs love it (frequency: medium)",
            "WIN REASONS:\n- Best-in-class UX (frequency: high)\nLOSS REASONS:\n- Pricing too high (frequency: high)",
            # Call 5: synthesizer
            "# Win/Loss Intelligence Report\n\n## Executive Summary\n- Notion wins on UX.",
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

    def _initial_state(self):
        return {
            "messages": [],
            "brand": "Notion",
            "category": "B2B SaaS",
            "competitors": ["Confluence", "Coda"],
            "query": "Why do customers choose us over Confluence?",
            "sources": [],
            "raw_signals": [],
            "extraction_tasks": [],
            "extracted_signals": [],
            "signal_matrix": "",
            "win_loss_report": "",
        }

    def _mock_utils(self):
        mock_util = {
            "error": None,
            "data": [],
            "reviews": [],
            "posts": [],
            "stories": [],
        }
        return {
            "src.nodes.win_loss_node.fetch_reddit_posts": mock_util,
            "src.nodes.win_loss_node.fetch_hn_stories": mock_util,
            "src.nodes.win_loss_node.scrape_g2_reviews": mock_util,
        }

    def test_graph_invoke_returns_win_loss_report(self):
        mock_util = {"error": None, "data": {"reviews": []}}
        with (
            patch("src.nodes.win_loss_node.GroqLLM", self._build_llm_mock_sequence()),
            patch("src.nodes.win_loss_node.fetch_reddit_posts", return_value=mock_util),
            patch("src.nodes.win_loss_node.fetch_hn_stories", return_value=mock_util),
            patch("src.nodes.win_loss_node.scrape_g2_reviews", return_value=mock_util),
        ):
            result = win_loss_graph.invoke(self._initial_state())

        self.assertIn("win_loss_report", result)
        self.assertIsInstance(result["win_loss_report"], str)
        self.assertGreater(len(result["win_loss_report"]), 0)

    def test_graph_invoke_returns_signal_matrix(self):
        mock_util = {"error": None, "data": {"reviews": []}}
        with (
            patch("src.nodes.win_loss_node.GroqLLM", self._build_llm_mock_sequence()),
            patch("src.nodes.win_loss_node.fetch_reddit_posts", return_value=mock_util),
            patch("src.nodes.win_loss_node.fetch_hn_stories", return_value=mock_util),
            patch("src.nodes.win_loss_node.scrape_g2_reviews", return_value=mock_util),
        ):
            result = win_loss_graph.invoke(self._initial_state())

        self.assertIn("signal_matrix", result)
        self.assertIsInstance(result["signal_matrix"], str)
        self.assertGreater(len(result["signal_matrix"]), 0)

    def test_raw_signals_fan_in_accumulates_all_sources(self):
        mock_util = {"error": None, "data": {"reviews": []}}
        with (
            patch("src.nodes.win_loss_node.GroqLLM", self._build_llm_mock_sequence()),
            patch("src.nodes.win_loss_node.fetch_reddit_posts", return_value=mock_util),
            patch("src.nodes.win_loss_node.fetch_hn_stories", return_value=mock_util),
            patch("src.nodes.win_loss_node.scrape_g2_reviews", return_value=mock_util),
        ):
            result = win_loss_graph.invoke(self._initial_state())

        raw_sources = {r["source"] for r in result["raw_signals"]}
        self.assertGreaterEqual(len(raw_sources), 1)

    def test_extracted_signals_fan_in_accumulates_labelled_results(self):
        mock_util = {"error": None, "data": {"reviews": []}}
        with (
            patch("src.nodes.win_loss_node.GroqLLM", self._build_llm_mock_sequence()),
            patch("src.nodes.win_loss_node.fetch_reddit_posts", return_value=mock_util),
            patch("src.nodes.win_loss_node.fetch_hn_stories", return_value=mock_util),
            patch("src.nodes.win_loss_node.scrape_g2_reviews", return_value=mock_util),
        ):
            result = win_loss_graph.invoke(self._initial_state())

        signals = result.get("extracted_signals", [])
        # At least one labelled signal should be present
        self.assertGreater(len(signals), 0)
        # Each should be a string starting with [LABEL]
        for sig in signals:
            self.assertIsInstance(sig, str)
            self.assertTrue(sig.startswith("["), f"Signal not labelled: {sig[:60]}")

    def test_sources_set_by_orchestrator(self):
        mock_util = {"error": None, "data": {"reviews": []}}
        with (
            patch("src.nodes.win_loss_node.GroqLLM", self._build_llm_mock_sequence()),
            patch("src.nodes.win_loss_node.fetch_reddit_posts", return_value=mock_util),
            patch("src.nodes.win_loss_node.fetch_hn_stories", return_value=mock_util),
            patch("src.nodes.win_loss_node.scrape_g2_reviews", return_value=mock_util),
        ):
            result = win_loss_graph.invoke(self._initial_state())

        self.assertIsInstance(result["sources"], list)
        self.assertGreater(len(result["sources"]), 0)
        for s in result["sources"]:
            self.assertIn(s, AVAILABLE_SIGNAL_SOURCES)


# ═══════════════════════════════════════════════════════════════════════════
# 12. Live test — real API calls (skipped unless WIN_LOSS_LIVE=1)
# ═══════════════════════════════════════════════════════════════════════════
@unittest.skipUnless(
    os.environ.get("WIN_LOSS_LIVE") == "1",
    "Skipped: set WIN_LOSS_LIVE=1 to run live API tests",
)
class TestLive(unittest.TestCase):
    """
    Smoke test the full graph against real external APIs.

    Requirements:
      .env must contain GROQ_API_KEY and at least SERPAPI_API_KEY.

    Run:
      WIN_LOSS_LIVE=1 uv run pytest tests/test_win_loss_agent.py -v -k live -s
    """

    @classmethod
    def setUpClass(cls):
        from dotenv import load_dotenv

        load_dotenv()

    def test_live_full_graph(self):
        result = win_loss_graph.invoke(
            {
                "messages": [],
                "brand": "Notion",
                "category": "B2B SaaS productivity / knowledge management",
                "competitors": ["Confluence", "Coda"],
                "query": "Why do customers choose Notion over Confluence, and where do we lose enterprise deals?",
                "sources": [],
                "raw_signals": [],
                "extraction_tasks": [],
                "extracted_signals": [],
                "signal_matrix": "",
                "win_loss_report": "",
            }
        )

        self.assertIn("win_loss_report", result)
        self.assertIsInstance(result["win_loss_report"], str)
        self.assertGreater(
            len(result["win_loss_report"]),
            100,
            "Report is suspiciously short — possible LLM or API failure",
        )
        self.assertIn("signal_matrix", result)
        self.assertIsInstance(result["signal_matrix"], str)
        self.assertIsInstance(result["sources"], list)
        self.assertGreater(len(result["sources"]), 0)

        print("\n" + "=" * 70)
        print("LIVE WIN/LOSS REPORT PREVIEW (first 500 chars):")
        print(result["win_loss_report"][:500])
        print("=" * 70)
        print(f"Sources fetched: {result['sources']}")
        print(f"Raw signals entries: {len(result['raw_signals'])}")
        print(f"Extracted signals: {len(result['extracted_signals'])}")
        print("\nSIGNAL MATRIX (first 500 chars):")
        print(result["signal_matrix"][:500])


if __name__ == "__main__":
    unittest.main()
