"""
test_adjacent_graph.py — LLM-as-Judge evaluation for the Adjacent Market Graph.

Run from the project root:
    python scripts/test_adjacent_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.adjacent_graph import adjacent_graph

GRAPH_NAME = "Adjacent Market Graph"
TEST_STATE = {
    "messages": [],
    "category": "Task Management SaaS for Creative Agencies",
    "fetched_content": [
        "Our product is a project management platform built for creative agencies. "
        "We have Kanban boards, time-tracking, client approval portals, and asset management. "
        "We charge $15/user/month. Main competitors are Asana, Monday.com, and ClickUp. "
        "But we focus specifically on the agency market."
    ],
}

CRITERIA = (
    "1. Must NOT focus on direct feature improvements — this is about ADJACENT threats, not roadmap.\n"
    "2. Must identify at least one 'Feature Absorption Threat' (e.g., Notion, Slack, MS Teams absorbing PM features).\n"
    "3. Must identify at least one horizontal tech disruption (AI task routing, autonomous project management agents).\n"
    "4. Must discuss at least one different 'Job To Be Done' alternative (e.g., clients using Figma+FigJam as a workflow).\n"
    "5. Must provide strategic defense vectors or 'pivot playbooks' against these threats.\n"
    "6. Output must be structured and specific (not vague generalizations)."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (may take 30-60s for parallel tool calls)")

    result_state = adjacent_graph.invoke(TEST_STATE)
    output = result_state.get("analysis_result", "")
    
    if not output:
        print("  ⚠ ERROR: No output returned from the graph!")
        sys.exit(1)

    print(f"  Output length: {len(output)} characters")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(GRAPH_NAME, output, CRITERIA)
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
