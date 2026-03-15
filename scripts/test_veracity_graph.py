"""
test_veracity_graph.py — LLM-as-Judge evaluation for the full Veracity orchestrator.

This tests the FULL graph pipeline: information_fetcher → 6 parallel sub-graphs → compiler_and_storage.

Run from the project root:
    python scripts/test_veracity_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.veracity_graph import veracity_graph

GRAPH_NAME = "Full Veracity Orchestrator"
TEST_STATE = {
    "brand": "AgencyFlow",
    "category": "Task Management SaaS for Creative Agencies",
    "query": "How do we reposition our pricing and messaging to win more mid-market agency deals in 2025?",
    "competitors": ["Asana", "Monday.com", "ClickUp"],
    "urls": ["https://asana.com/pricing"],  # Single URL to keep runtime manageable
    "pdf_paths": [],
    "txt_paths": [],
}

CRITERIA = (
    "1. The graph must successfully produce 6 sub-graph analysis results (adjacent, competitor, market_trend, pricing, user_voice, win_loss).\n"
    "2. A `compiled_report` must be present in the final state with all 6 sub-analyses.\n"
    "3. `storage_status` must confirm successful ChromaDB persistence.\n"
    "4. Each sub-analysis must be non-empty (no silent failures).\n"
    "5. The orchestration must not hallucinate or fabricate competitor names outside the provided three.\n"
    "6. Overall the output must be coherent and relevant to the brand 'AgencyFlow' in the task management SaaS space."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking FULL veracity_graph pipeline...")
    print("  (This will invoke information_fetcher + 6 parallel sub-graphs + compiler)")
    print("  Expected runtime: 2-5 minutes\n")

    result_state = veracity_graph.invoke(TEST_STATE)

    compiled_report = result_state.get("compiled_report", {})
    storage_status = result_state.get("storage_status", "")
    analyses = compiled_report.get("analyses", {})

    # Assemble a summary of what was produced
    summary_parts = [f"COMPILED REPORT OVERVIEW:"]
    summary_parts.append(f"  - Category: {compiled_report.get('category')}")
    summary_parts.append(f"  - Timestamp: {compiled_report.get('timestamp')}")
    summary_parts.append(f"  - Storage Status: {storage_status}")
    summary_parts.append(f"\nSUB-GRAPH RESULTS:")

    for key, value in analyses.items():
        snippet = str(value)[:200]
        status = "✓ Present" if value else "✗ Empty"
        summary_parts.append(f"  [{status}] {key}: {snippet}...")

    output = "\n".join(summary_parts)

    print(f"  Sub-graph results: {len([v for v in analyses.values() if v])}/6 completed")
    print(f"  Storage status: {storage_status[:80]}")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(
        GRAPH_NAME, output, CRITERIA,
        extra_context=f"Storage outcome was: {storage_status}"
    )
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
