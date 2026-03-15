"""
Tests for src/utils/persistence_utils.py

All tests use a temporary directory for the ChromaDB store so they never
touch the real chroma_db/ directory and never interfere with each other.

The module-level singleton (_client) is reset between tests by patching
CHROMA_PERSIST_DIR and resetting the _client global.
"""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from typing import Generator
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_persistence(tmp_path: str):
    """Reload persistence_utils with a fresh client pointing at tmp_path."""
    import src.utils.persistence_utils as pu

    pu._client = None  # reset singleton
    pu.CHROMA_PERSIST_DIR = tmp_path
    return pu


@pytest.fixture()
def pu(tmp_path):
    """Return a freshly-initialised persistence_utils module using a temp DB."""
    import src.utils.persistence_utils as mod

    original_dir = mod.CHROMA_PERSIST_DIR
    original_client = mod._client
    mod._client = None
    mod.CHROMA_PERSIST_DIR = str(tmp_path)
    yield mod
    # Restore
    mod._client = original_client
    mod.CHROMA_PERSIST_DIR = original_dir


# ===========================================================================
# _get_client / _get_collection
# ===========================================================================


class TestGetClient:
    def test_returns_persistent_client(self, pu, tmp_path):
        import chromadb

        client = pu._get_client()
        # PersistentClient is a factory function in chromadb, so check the
        # underlying type via the chromadb.api module instead.
        assert hasattr(client, "get_or_create_collection")
        assert hasattr(client, "get_collection")

    def test_singleton_same_object(self, pu):
        c1 = pu._get_client()
        c2 = pu._get_client()
        assert c1 is c2

    def test_creates_persist_dir(self, pu, tmp_path):
        subdir = str(tmp_path / "new_subdir")
        pu._client = None
        pu.CHROMA_PERSIST_DIR = subdir
        pu._get_client()
        assert os.path.isdir(subdir)


class TestGetCollection:
    def test_creates_collection(self, pu):
        col = pu._get_collection("test_col")
        assert col is not None
        assert col.name == "test_col"

    def test_idempotent(self, pu):
        c1 = pu._get_collection("idempotent_col")
        c2 = pu._get_collection("idempotent_col")
        assert c1.name == c2.name


# ===========================================================================
# _safe_json
# ===========================================================================


class TestSafeJson:
    def test_dict_serialises(self, pu):
        result = pu._safe_json({"a": 1, "b": [2, 3]})
        assert '"a"' in result
        assert '"b"' in result

    def test_truncates_at_max_chars(self, pu):
        big = {"key": "x" * 20_000}
        result = pu._safe_json(big, max_chars=100)
        assert len(result) <= 101  # 100 + ellipsis char
        assert result.endswith("…")

    def test_no_truncation_when_small(self, pu):
        result = pu._safe_json({"k": "v"}, max_chars=1000)
        assert "…" not in result

    def test_non_serialisable_falls_back_to_str(self, pu):
        class _Unser:
            def __repr__(self):
                return "custom_repr"

        result = pu._safe_json(_Unser())
        assert result  # non-empty

    def test_empty_dict(self, pu):
        assert pu._safe_json({}) == "{}"


# ===========================================================================
# persist_graph_run
# ===========================================================================


class TestPersistGraphRun:
    def test_returns_session_id_string(self, pu):
        sid = pu.persist_graph_run(
            graph_name="test_graph",
            state={"result": "ok"},
        )
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_uses_supplied_session_id(self, pu):
        supplied = str(uuid.uuid4())
        sid = pu.persist_graph_run(
            graph_name="test_graph",
            state={"result": "ok"},
            session_id=supplied,
        )
        assert sid == supplied

    def test_auto_generates_session_id(self, pu):
        sid = pu.persist_graph_run(
            graph_name="test_graph",
            state={},
        )
        # Should be a valid UUID
        uuid.UUID(sid)  # raises if not valid

    def test_document_stored_in_collection(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            graph_name="g1",
            state={"x": 1},
            session_id=sid,
        )
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        assert col.count() >= 1

    def test_upsert_does_not_duplicate(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run("g1", {"v": 1}, session_id=sid)
        pu.persist_graph_run("g1", {"v": 2}, session_id=sid)
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        # Same session_id → same doc id → count should still be 1
        assert col.count() == 1

    def test_metadata_fields_stored(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            graph_name="meta_graph",
            state={"r": "v"},
            session_id=sid,
            brand="Acme",
            category="SaaS",
            query="test query",
        )
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        doc = col.get(ids=[f"meta_graph/{sid}"])
        meta = doc["metadatas"][0]
        assert meta["graph_name"] == "meta_graph"
        assert meta["brand"] == "Acme"
        assert meta["category"] == "SaaS"
        assert meta["query"] == "test query"
        assert "timestamp" in meta
        assert "session_id" in meta

    def test_extra_metadata_stored(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            "g_extra",
            {},
            session_id=sid,
            extra_metadata={"custom_int": 42, "custom_bool": True, "custom_str": "hi"},
        )
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        doc = col.get(ids=[f"g_extra/{sid}"])
        meta = doc["metadatas"][0]
        assert meta["custom_int"] == 42
        assert meta["custom_bool"] is True
        assert meta["custom_str"] == "hi"

    def test_non_scalar_extra_metadata_coerced_to_str(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            "g_coerce",
            {},
            session_id=sid,
            extra_metadata={"nested": {"a": 1}},
        )
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        doc = col.get(ids=[f"g_coerce/{sid}"])
        assert isinstance(doc["metadatas"][0]["nested"], str)

    def test_different_graphs_stored_separately(self, pu):
        pu.persist_graph_run("graph_a", {"a": 1}, session_id="s1")
        pu.persist_graph_run("graph_b", {"b": 2}, session_id="s1")
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        assert col.count() == 2

    def test_document_text_contains_query(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            "g_text",
            {},
            session_id=sid,
            query="unique_query_string_xyz",
        )
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        doc = col.get(ids=[f"g_text/{sid}"])
        assert "unique_query_string_xyz" in doc["documents"][0]

    def test_query_truncated_in_metadata_at_500_chars(self, pu):
        sid = str(uuid.uuid4())
        long_query = "q" * 600
        pu.persist_graph_run("g_q", {}, session_id=sid, query=long_query)
        col = pu._get_collection(pu.COLLECTION_GRAPH_RUNS)
        doc = col.get(ids=[f"g_q/{sid}"])
        assert len(doc["metadatas"][0]["query"]) <= 500


# ===========================================================================
# retrieve_past_runs
# ===========================================================================


class TestRetrievePastRuns:
    def test_returns_empty_on_empty_collection(self, pu):
        results = pu.retrieve_past_runs("nonexistent_graph", "anything")
        assert results == []

    def test_returns_list_of_dicts(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_graph_run(
            "search_graph", {"data": "hello world"}, session_id=sid, query="hello"
        )
        results = pu.retrieve_past_runs("search_graph", "hello")
        assert isinstance(results, list)
        for r in results:
            assert "id" in r
            assert "document" in r
            assert "metadata" in r
            assert "distance" in r

    def test_filters_by_graph_name(self, pu):
        pu.persist_graph_run("graph_x", {}, session_id="sx1", query="foo")
        pu.persist_graph_run("graph_y", {}, session_id="sy1", query="foo")
        results = pu.retrieve_past_runs("graph_x", "foo")
        for r in results:
            assert r["metadata"]["graph_name"] == "graph_x"

    def test_filters_by_brand(self, pu):
        pu.persist_graph_run("bg", {}, session_id="b1", brand="BrandA", query="q")
        pu.persist_graph_run("bg", {}, session_id="b2", brand="BrandB", query="q")
        results = pu.retrieve_past_runs("bg", "q", brand="BrandA")
        assert all(r["metadata"]["brand"] == "BrandA" for r in results)

    def test_filters_by_category(self, pu):
        pu.persist_graph_run("cg", {}, session_id="c1", category="CatA", query="q")
        pu.persist_graph_run("cg", {}, session_id="c2", category="CatB", query="q")
        results = pu.retrieve_past_runs("cg", "q", category="CatA")
        assert all(r["metadata"]["category"] == "CatA" for r in results)

    def test_n_results_respected(self, pu):
        for i in range(5):
            pu.persist_graph_run(
                "nr_graph", {"i": i}, session_id=f"nr_{i}", query=f"item {i}"
            )
        results = pu.retrieve_past_runs("nr_graph", "item", n_results=2)
        assert len(results) <= 2

    def test_returns_empty_when_no_match_for_graph(self, pu):
        pu.persist_graph_run("present_graph", {}, session_id="p1", query="test")
        results = pu.retrieve_past_runs("absent_graph", "test")
        assert results == []


# ===========================================================================
# persist_conversation_turn
# ===========================================================================


class TestPersistConversationTurn:
    def test_stores_turn(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "Hello!")
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        assert col.count() == 1

    def test_multiple_turns_increment_index(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "Turn 0")
        pu.persist_conversation_turn(sid, "ai", "Turn 1")
        pu.persist_conversation_turn(sid, "human", "Turn 2")
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        assert col.count() == 3

    def test_turn_metadata_fields(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(
            sid, "human", "msg", graph_name="my_graph", brand="Brand"
        )
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        results = col.get(where={"session_id": {"$eq": sid}})
        meta = results["metadatas"][0]
        assert meta["role"] == "human"
        assert meta["session_id"] == sid
        assert meta["graph_name"] == "my_graph"
        assert meta["brand"] == "Brand"
        assert meta["turn_index"] == 0
        assert "timestamp" in meta

    def test_document_contains_content(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "ai", "This is the AI reply.")
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        results = col.get(where={"session_id": {"$eq": sid}})
        assert "This is the AI reply." in results["documents"][0]

    def test_document_contains_role_prefix(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "system", "System message.")
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        results = col.get(where={"session_id": {"$eq": sid}})
        assert results["documents"][0].startswith("[SYSTEM]")

    def test_different_sessions_isolated(self, pu):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        pu.persist_conversation_turn(sid_a, "human", "Session A msg")
        pu.persist_conversation_turn(sid_b, "human", "Session B msg")
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        res_a = col.get(where={"session_id": {"$eq": sid_a}})
        res_b = col.get(where={"session_id": {"$eq": sid_b}})
        assert len(res_a["ids"]) == 1
        assert len(res_b["ids"]) == 1

    def test_extra_metadata_stored(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(
            sid, "human", "msg", extra_metadata={"ui_version": "2.0"}
        )
        col = pu._get_collection(pu.COLLECTION_CONVERSATIONS)
        results = col.get(where={"session_id": {"$eq": sid}})
        assert results["metadatas"][0]["ui_version"] == "2.0"


# ===========================================================================
# retrieve_conversation
# ===========================================================================


class TestRetrieveConversation:
    def test_returns_empty_for_unknown_session(self, pu):
        result = pu.retrieve_conversation("no_such_session")
        assert result == []

    def test_returns_all_turns(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "Hi")
        pu.persist_conversation_turn(sid, "ai", "Hello!")
        turns = pu.retrieve_conversation(sid)
        assert len(turns) == 2

    def test_turns_sorted_by_turn_index(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "First")
        pu.persist_conversation_turn(sid, "ai", "Second")
        pu.persist_conversation_turn(sid, "human", "Third")
        turns = pu.retrieve_conversation(sid)
        indices = [t["turn_index"] for t in turns]
        assert indices == sorted(indices)

    def test_turn_fields_present(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "Content here")
        turns = pu.retrieve_conversation(sid)
        t = turns[0]
        assert "id" in t
        assert "role" in t
        assert "content" in t
        assert "turn_index" in t
        assert "timestamp" in t
        assert "metadata" in t

    def test_role_preserved(self, pu):
        sid = str(uuid.uuid4())
        pu.persist_conversation_turn(sid, "human", "Msg1")
        pu.persist_conversation_turn(sid, "ai", "Msg2")
        turns = pu.retrieve_conversation(sid)
        roles = [t["role"] for t in turns]
        assert roles[0] == "human"
        assert roles[1] == "ai"

    def test_empty_on_empty_db(self, pu):
        result = pu.retrieve_conversation("ghost_session")
        assert result == []

    def test_does_not_mix_sessions(self, pu):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        pu.persist_conversation_turn(sid_a, "human", "A1")
        pu.persist_conversation_turn(sid_a, "ai", "A2")
        pu.persist_conversation_turn(sid_b, "human", "B1")
        turns_a = pu.retrieve_conversation(sid_a)
        turns_b = pu.retrieve_conversation(sid_b)
        assert len(turns_a) == 2
        assert len(turns_b) == 1


# ===========================================================================
# Constants / module-level attributes
# ===========================================================================


class TestConstants:
    def test_collection_names_are_strings(self, pu):
        assert isinstance(pu.COLLECTION_GRAPH_RUNS, str)
        assert isinstance(pu.COLLECTION_CONVERSATIONS, str)

    def test_collection_names_non_empty(self, pu):
        assert pu.COLLECTION_GRAPH_RUNS
        assert pu.COLLECTION_CONVERSATIONS

    def test_chroma_persist_dir_is_string(self, pu):
        assert isinstance(pu.CHROMA_PERSIST_DIR, str)


# ===========================================================================
# Integration: __init__.py exports
# ===========================================================================


class TestInitExports:
    def test_persist_graph_run_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "persist_graph_run")

    def test_retrieve_past_runs_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "retrieve_past_runs")

    def test_persist_conversation_turn_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "persist_conversation_turn")

    def test_retrieve_conversation_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "retrieve_conversation")

    def test_constants_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "COLLECTION_GRAPH_RUNS")
        assert hasattr(utils_pkg, "COLLECTION_CONVERSATIONS")
        assert hasattr(utils_pkg, "CHROMA_PERSIST_DIR")

    def test_deprecated_shims_still_exported(self):
        import src.utils as utils_pkg

        assert hasattr(utils_pkg, "store_to_chromadb")
        assert hasattr(utils_pkg, "query_chromadb")
