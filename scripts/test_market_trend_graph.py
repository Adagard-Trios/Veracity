"""
test_market_trend_graph.py — LLM-as-Judge evaluation for the Market Trend Graph.

Run from the project root:
    python scripts/test_market_trend_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.marketing_trend_graph import marketing_trend_graph

GRAPH_NAME = "Market Trend Graph"
TEST_STATE = {
    "messages": [],
    "brand": "AgencyFlow",
    "category": "Task Management SaaS for Creative Agencies",
    "query": "What are the biggest shifts in how creative agencies are managing projects, and what new tools are capturing budget?",
    "sources": [],
    "raw_data": [],
    "analysis_tasks": [],
    "analysis_results": [],
    "analysis_report": "",
}

CRITERIA = (
    "1. Must identify macro buyer behavior shifts in the target market (not generic tech trends).\n"
    "2. Must surface emerging competitor ad spend or narrative patterns from ads/news data.\n"
    "3. Must identify at least one growth opportunity or underserved segment.\n"
    "4. Must include data-backed signals (e.g. search trends, ad spend, Reddit signals).\n"
    "5. Analysis must be specific to 'creative agencies' — generic SaaS trends do not count.\n"
    "6. Must produce an `analysis_report` field as the primary output."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (includes dual-phase parallel fan-out via Send API)")

    result_state = marketing_trend_graph.invoke(TEST_STATE)
    output = result_state.get("analysis_report", "")
    
    if not output:
        print("  ⚠ ERROR: No output returned from the graph!")
        sys.exit(1)

    print(f"  Output length: {len(output)} characters")
    print(f"  Raw data items collected: {len(result_state.get('raw_data', []))}")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(GRAPH_NAME, output, CRITERIA)
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
