"""
test_competitor_graph.py — LLM-as-Judge evaluation for the Competitor Analysis Graph.

Run from the project root:
    python scripts/test_competitor_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.competitor_graph import competitor_graph

GRAPH_NAME = "Competitor Analysis Graph"
TEST_STATE = {
    "messages": [],
    "category": "Task Management SaaS for Creative Agencies",
    "fetched_content": [
        "Our product is a project management platform built for creative agencies. "
        "We have Kanban boards, time-tracking, client approval portals, and asset management. "
        "We charge $15/user/month. Main competitors are Asana, Monday.com, and ClickUp. "
        "We focus specifically on the creative agency market."
    ],
    "competitor_tasks": [],
    "competitor_results": [],
    "analysis_result": "",
    "structured_output": {},
}

CRITERIA = (
    "1. Must identify at least 3 distinct direct competitors.\n"
    "2. Must include a real SWOT or comparative analysis (not just high-level messaging).\n"
    "3. Must analyze competitor positioning and differentiation claims.\n"
    "4. Must identify specific feature gaps or weaknesses in our product vs competitors.\n"
    "5. Output must have a `structured_output` field with an `overall_confidence` score.\n"
    "6. Analysis should be specific to the task management/agency domain (not generic)."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (includes parallel Firecrawl fetches per competitor)")

    result_state = competitor_graph.invoke(TEST_STATE)
    output = result_state.get("analysis_result", "")
    structured = result_state.get("structured_output", {})
    
    if not output:
        print("  ⚠ ERROR: No output returned from the graph!")
        sys.exit(1)

    print(f"  Output length: {len(output)} characters")
    print(f"  Structured output keys: {list(structured.keys()) if structured else 'None'}")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(
        GRAPH_NAME, output, CRITERIA,
        extra_context=f"Structured output was: {str(structured)[:300]}"
    )
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
