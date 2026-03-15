"""
Persistence Utilities — Scalable ChromaDB persistence for all LangGraph graph runs.

Design goals
------------
* One module, works for every graph (veracity, marketing_trend, win_loss, …).
* Modern API: chromadb.PersistentClient(path=...) — no deprecated Settings hack.
* Upsert (not add) so re-running the same session never duplicates documents.
* Rich metadata on every document: graph_name, session_id, run_id, timestamp,
  brand/category, and arbitrary extra fields.
* Lazy singleton client — the client is created once per process and reused,
  avoiding repeated file-lock acquisitions on the SQLite backend.
* Two public surfaces:
    persist_graph_run()        — save a completed graph invocation
    retrieve_past_runs()       — semantic search over past runs for a graph
    persist_conversation_turn()— save one message from a chat conversation
    retrieve_conversation()    — fetch the full history for a session

Collections created
-------------------
  graph_runs        — one document per graph invocation (all graph types)
  conversations     — one document per message turn (all sessions)

A single "graph_runs" collection (rather than one per graph) scales better:
- No collection-proliferation as new graphs are added.
- Cross-graph retrieval is straightforward via metadata filters.
- ChromaDB handles per-graph filtering through the `graph_name` metadata field.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import chromadb

# ---------------------------------------------------------------------------
# Path resolution — always relative to this file so imports work from any cwd
# ---------------------------------------------------------------------------
_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_UTILS_DIR, "..", ".."))
CHROMA_PERSIST_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------
COLLECTION_GRAPH_RUNS = "graph_runs"
COLLECTION_CONVERSATIONS = "conversations"

# ---------------------------------------------------------------------------
# Lazy singleton client
# ---------------------------------------------------------------------------
_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    """Return the module-level PersistentClient, creating it on first call."""
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _get_collection(name: str) -> chromadb.Collection:
    """Return (or create) a named collection."""
    return _get_client().get_or_create_collection(name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_json(obj: Any, max_chars: int = 10_000) -> str:
    """Serialise *obj* to a JSON string, truncating to *max_chars*."""
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_run_id(graph_name: str, session_id: str) -> str:
    """Deterministic doc-ID for a graph run: <graph>/<session>.

    Using a deterministic ID means that calling persist_graph_run() multiple
    times for the same session always *updates* (upserts) the stored document
    rather than creating duplicates.
    """
    return f"{graph_name}/{session_id}"


def _build_turn_id(session_id: str, turn_index: int) -> str:
    """Deterministic doc-ID for a conversation turn."""
    return f"conv/{session_id}/{turn_index:06d}"


# ---------------------------------------------------------------------------
# Public API — graph run persistence
# ---------------------------------------------------------------------------


def persist_graph_run(
    graph_name: str,
    state: dict[str, Any],
    *,
    session_id: str | None = None,
    brand: str = "",
    category: str = "",
    query: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> str:
    """Persist a completed graph run to ChromaDB.

    Parameters
    ----------
    graph_name:
        Logical name of the graph, e.g. "veracity_graph", "win_loss_graph",
        "marketing_trend_graph".
    state:
        The final LangGraph state dict returned by the graph invocation.
        Large nested objects are JSON-serialised and truncated to fit within
        ChromaDB's document size limits.
    session_id:
        Caller-supplied stable identifier for this logical session (e.g. a
        UUID tied to a user session or API request).  If omitted a new UUID
        is generated.
    brand:
        Brand name associated with the run — stored as metadata for filtering.
    category:
        Category/market segment — stored as metadata for filtering.
    query:
        Original research question or user query — stored as both document
        text (for semantic search) and metadata.
    extra_metadata:
        Any additional key/value pairs to attach to the document.  Values must
        be str, int, float, or bool (ChromaDB metadata constraint).

    Returns
    -------
    The session_id used (either the one supplied or the auto-generated one).
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    doc_id = _build_run_id(graph_name, session_id)
    timestamp = _utc_now_iso()

    # Build the document text: query + compact state summary for semantic search
    doc_text = (
        f"Graph: {graph_name}\n"
        f"Brand: {brand}\n"
        f"Category: {category}\n"
        f"Query: {query}\n"
        f"Timestamp: {timestamp}\n\n"
        f"State summary:\n{_safe_json(state)}"
    )

    # Metadata — all values must be str/int/float/bool
    metadata: dict[str, str | int | float | bool] = {
        "graph_name": graph_name,
        "session_id": session_id,
        "brand": brand,
        "category": category,
        "query": query[:500],  # cap length for metadata field
        "timestamp": timestamp,
    }
    if extra_metadata:
        for k, v in extra_metadata.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[k] = v
            else:
                metadata[k] = str(v)

    col = _get_collection(COLLECTION_GRAPH_RUNS)
    col.upsert(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[metadata],
    )

    return session_id


def retrieve_past_runs(
    graph_name: str,
    query: str,
    *,
    n_results: int = 5,
    brand: str = "",
    category: str = "",
) -> list[dict[str, Any]]:
    """Semantic search over past graph runs.

    Parameters
    ----------
    graph_name:
        Restrict results to runs from this graph.
    query:
        Natural-language search query.
    n_results:
        Maximum number of results to return.
    brand:
        If non-empty, restrict results to runs with this brand.
    category:
        If non-empty, restrict results to runs with this category.

    Returns
    -------
    List of dicts, each with keys: ``id``, ``document``, ``metadata``,
    ``distance``.  Sorted by relevance (closest first).
    """
    col = _get_collection(COLLECTION_GRAPH_RUNS)

    # Check if the collection has any documents first
    if col.count() == 0:
        return []

    # Build the where clause
    filters: list[dict] = [{"graph_name": {"$eq": graph_name}}]
    if brand:
        filters.append({"brand": {"$eq": brand}})
    if category:
        filters.append({"category": {"$eq": category}})

    where = filters[0] if len(filters) == 1 else {"$and": filters}

    try:
        results = col.query(
            query_texts=[query],
            n_results=min(n_results, col.count()),
            where=where,
        )
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    ids = (results.get("ids") or [[]])[0]
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
        out.append(
            {
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": dist,
            }
        )

    return out


# ---------------------------------------------------------------------------
# Public API — conversation persistence
# ---------------------------------------------------------------------------


def persist_conversation_turn(
    session_id: str,
    role: str,
    content: str,
    *,
    graph_name: str = "",
    brand: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a single conversation turn (one message) to ChromaDB.

    Each turn gets a deterministic ID based on session_id + turn index so that
    calling this function again for the same turn is idempotent (upsert).

    Parameters
    ----------
    session_id:
        Stable identifier for the conversation session.
    role:
        Message role: "human", "ai", "system", etc.
    content:
        The message text.
    graph_name:
        Optional graph that produced this turn (for filtering).
    brand:
        Optional brand context.
    extra_metadata:
        Additional scalar metadata.
    """
    col = _get_collection(COLLECTION_CONVERSATIONS)

    # Determine the next turn index by counting existing turns for this session
    existing = col.get(where={"session_id": {"$eq": session_id}})
    turn_index = len((existing.get("ids") or []))

    doc_id = _build_turn_id(session_id, turn_index)
    timestamp = _utc_now_iso()

    doc_text = f"[{role.upper()}] {content}"

    metadata: dict[str, str | int | float | bool] = {
        "session_id": session_id,
        "role": role,
        "turn_index": turn_index,
        "graph_name": graph_name,
        "brand": brand,
        "timestamp": timestamp,
    }
    if extra_metadata:
        for k, v in extra_metadata.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[k] = v
            else:
                metadata[k] = str(v)

    col.upsert(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[metadata],
    )


def retrieve_conversation(session_id: str) -> list[dict[str, Any]]:
    """Retrieve the full ordered conversation history for a session.

    Returns
    -------
    List of dicts with keys: ``role``, ``content``, ``turn_index``,
    ``timestamp``, ``metadata``.  Sorted by ``turn_index`` ascending.
    """
    col = _get_collection(COLLECTION_CONVERSATIONS)

    if col.count() == 0:
        return []

    try:
        results = col.get(
            where={"session_id": {"$eq": session_id}},
            include=["documents", "metadatas"],
        )
    except Exception:
        return []

    ids = results.get("ids") or []
    docs = results.get("documents") or []
    metas = results.get("metadatas") or []

    turns: list[dict[str, Any]] = []
    for doc_id, doc, meta in zip(ids, docs, metas):
        turns.append(
            {
                "id": doc_id,
                "role": meta.get("role", ""),
                "content": doc,
                "turn_index": meta.get("turn_index", 0),
                "timestamp": meta.get("timestamp", ""),
                "metadata": meta,
            }
        )

    return sorted(turns, key=lambda t: t["turn_index"])
