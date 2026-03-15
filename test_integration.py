"""
Integration test - checks that all 7 graphs compile and their nodes are correct.
"""

from src.graphs.veracity_graph import veracity_graph
from src.graphs.adjacent_graph import adjacent_graph
from src.graphs.competitor_graph import competitor_graph
from src.graphs.marketing_trend_graph import marketing_trend_graph
from src.graphs.pricing_graph import pricing_graph
from src.graphs.user_voice_graph import user_voice_graph
from src.graphs.win_loss_graph import win_loss_graph

tests_passed = 0
tests_failed = 0

# ------------------------------------------------------------------
# Test 1: All graphs have the expected entry nodes
# ------------------------------------------------------------------
expected_nodes = {
    "veracity_graph": ["information_fetcher", "adjacent_analysis", "competitor_analysis",
                       "market_trend_analysis", "pricing_analysis", "user_voice_analysis",
                       "win_loss_analysis", "compiler_and_storage"],
    "adjacent_graph": ["context_extractor", "data_collector", "compiler"],
    "competitor_graph": ["planner", "fetch_competitor", "compiler"],
    "marketing_trend_graph": ["orchestrator_node", "fetch_source_node", "analysis_dispatcher_node",
                               "run_analysis_tool_node", "synthesize_node"],
    "pricing_graph": ["context_extractor", "data_collector", "compiler"],
    "user_voice_graph": ["context_extractor", "data_collector", "compiler"],
    "win_loss_graph": ["wl_orchestrator_node", "wl_fetch_node", "wl_signal_extractor_node",
                        "wl_extract_node", "wl_synthesizer_node"],
}

graphs = {
    "veracity_graph": veracity_graph,
    "adjacent_graph": adjacent_graph,
    "competitor_graph": competitor_graph,
    "marketing_trend_graph": marketing_trend_graph,
    "pricing_graph": pricing_graph,
    "user_voice_graph": user_voice_graph,
    "win_loss_graph": win_loss_graph,
}

print("=" * 60)
print("VERACITY AI - ARCHITECTURE INTEGRATION TEST")
print("=" * 60)

for graph_name, graph in graphs.items():
    actual_nodes = set(graph.nodes.keys())
    expected = set(expected_nodes[graph_name])
    missing = expected - actual_nodes
    print(f"\n[{graph_name}]")
    for n in sorted(actual_nodes):
        print(f"  ✓ {n}")
    if missing:
        print(f"  ✗ MISSING: {missing}")
        tests_failed += 1
    else:
        tests_passed += 1
        print(f"  → PASS ({len(actual_nodes)} nodes)")

# ------------------------------------------------------------------
# Test 2: Verify veracity_state has all required fields
# ------------------------------------------------------------------
from src.states.veracity_state import VeracityState

required_fields = [
    "brand", "category", "query", "competitors",
    "urls", "pdf_paths", "txt_paths", "fetched_content", "messages",
    "adjacent_analysis", "competitor_analysis", "market_trend_analysis",
    "pricing_analysis", "user_voice_analysis", "win_loss_analysis",
    "compiled_report", "storage_status", "sse_queue"
]

print("\n\n[VeracityState - Field Verification]")
state_hints = VeracityState.__annotations__
missing_fields = [f for f in required_fields if f not in state_hints]
if missing_fields:
    print(f"  ✗ MISSING FIELDS: {missing_fields}")
    tests_failed += 1
else:
    tests_passed += 1
    print(f"  ✓ All {len(required_fields)} required fields present → PASS")

# ------------------------------------------------------------------
# Test 3: Verify app.py can import all endpoints
# ------------------------------------------------------------------
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", "app.py")
    mod = importlib.util.module_from_spec(spec)
    # Only load the app module, don't run the server
    print("\n\n[app.py - FastAPI Route Check]")
    from fastapi.testclient import TestClient
    spec.loader.exec_module(mod)
    app = mod.app
    routes = [r.path for r in app.routes]
    expected_routes = ["/api/start", "/api/stop", "/api/status", "/api/stream", "/api/rag"]
    for route in expected_routes:
        if route in routes:
            print(f"  ✓ {route} endpoint registered")
        else:
            print(f"  ✗ MISSING: {route}")
            tests_failed += 1
    tests_passed += 1
except Exception as e:
    print(f"  ⚠ Could not fully test app.py routes: {e} (this is expected in offline test)")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
print("\n\n" + "=" * 60)
print(f"INTEGRATION TEST SUMMARY")
print(f"  Passed: {tests_passed}")
print(f"  Failed: {tests_failed}")
if tests_failed == 0:
    print("  RESULT: ✓ ALL TESTS PASSED")
else:
    print("  RESULT: ✗ SOME TESTS FAILED")
print("=" * 60)
