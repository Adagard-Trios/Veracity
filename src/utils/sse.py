"""
SSE emit utilities — shared between veracity_graph.py and veracity_node.py.

Kept in src/utils/ to avoid circular imports:
  veracity_graph  → imports veracity_node
  veracity_node   → cannot import from veracity_graph (cycle)
  both            → can safely import from src.utils.sse
"""

import json


DOMAIN_AGENT_ID_MAP = {
    "competitive_landscape": 3,
    "market_trends": 2,
    "win_loss": 4,
    "pricing_packaging": 5,
    "positioning": 6,
    "adjacent_markets": 7,
}


def emit_sse_artifact(domain: str, payload: dict, confidence: float, sse_queue) -> None:
    """
    Pushes two SSE events to the queue consumed by the /api/stream endpoint:
      1. artifact_update — structured payload for the frontend dashboard card
      2. agent_complete  — signals the agent status pill to show green + confidence

    sse_queue must be a thread-safe queue.Queue or equivalent.
    Pass None during unit tests — this function becomes a no-op.
    The event JSON structure (type, domain, payload, agentId, confidence) must
    stay exactly as shown — the frontend validates this shape with Zod and will
    silently discard non-conforming events.
    """
    if sse_queue is None:
        return

    artifact_event = {
        "type": "artifact_update",
        "domain": domain,
        "payload": payload,
    }
    sse_queue.put(f"data: {json.dumps(artifact_event)}\n\n")

    complete_event = {
        "type": "agent_complete",
        "agentId": DOMAIN_AGENT_ID_MAP.get(domain, 3),
        "confidence": round(confidence, 3),
    }
    sse_queue.put(f"data: {json.dumps(complete_event)}\n\n")
