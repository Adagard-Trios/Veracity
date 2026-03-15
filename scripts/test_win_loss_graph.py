"""
test_win_loss_graph.py — LLM-as-Judge evaluation for the Win/Loss Intelligence Graph.

Run from the project root:
    python scripts/test_win_loss_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.win_loss_graph import win_loss_graph

GRAPH_NAME = "Win/Loss Intelligence Graph"
TEST_STATE = {
    "messages": [],
    "brand": "AgencyFlow",
    "category": "Task Management SaaS for Creative Agencies",
    "competitors": ["Asana", "Monday.com", "ClickUp"],
    "query": "Why are we losing deals to Monday.com in the mid-market segment, and how can we flip the narrative?",
    "sources": [],
    "raw_signals": [],
    "extraction_tasks": [],
    "extracted_signals": [],
    "signal_matrix": "",
    "win_loss_report": "",
}

CRITERIA = (
    "1. Must surface real buyer signals from community and review data (G2, Capterra, Reddit, HN).\n"
    "2. Must produce a Win/Loss Signal Matrix with clear data dimensions (by source, sentiment, theme).\n"
    "3. Must identify specific reasons deals are lost (e.g., pricing, missing features, onboarding friction).\n"
    "4. Must identify specific reasons deals are won (differentiators that resonate).\n"
    "5. Must provide an evidence-backed executive report — not generic advice.\n"
    "6. Analysis must be specific to the competitors named (Asana, Monday.com, ClickUp) — not generic."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (includes dual-phase parallel fan-out via Send API)")

    result_state = win_loss_graph.invoke(TEST_STATE)
    output = result_state.get("win_loss_report", "")
    signal_matrix = result_state.get("signal_matrix", "")
    
    if not output:
        print("  ⚠ ERROR: No win_loss_report returned from the graph!")
        sys.exit(1)

    full_output = f"REPORT:\n{output}\n\nSIGNAL MATRIX:\n{signal_matrix}"
    print(f"  Win/Loss Report length: {len(output)} characters")
    print(f"  Signal Matrix length: {len(signal_matrix)} characters")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(GRAPH_NAME, full_output, CRITERIA)
    filepath = save_test_result(GRAPH_NAME, evaluation, full_output)
    print_result(evaluation, filepath)
