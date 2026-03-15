"""
test_pricing_graph.py — LLM-as-Judge evaluation for the Pricing Analysis Graph.

Run from the project root:
    python scripts/test_pricing_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.pricing_graph import pricing_graph

GRAPH_NAME = "Pricing Analysis Graph"
TEST_STATE = {
    "messages": [],
    "category": "Task Management SaaS for Creative Agencies",
    "fetched_content": [
        "Our product is a project management platform built for creative agencies. "
        "We have Kanban boards, time-tracking, client approval portals, and asset management. "
        "We charge $15/user/month. Main competitors are Asana, Monday.com, and ClickUp."
    ],
    "extracted_context": "",
    "serp_results": "",
    "meta_ad_results": "",
    "scraped_pricing_pages": "",
    "reddit_results": "",
    "hn_results": "",
    "linkedin_ad_results": "",
    "content_analysis": "",
    "analysis_result": "",
}

CRITERIA = (
    "1. Must benchmark pricing models in the market (per-user/seat, freemium, flat-rate, usage-based).\n"
    "2. Must surface real willingness-to-pay signals from user discussion data (Reddit/HN/community).\n"
    "3. Must analyze actual competitor pricing pages (not just state their price — must compare tiers/features).\n"
    "4. Must include a recommended pricing strategy or at least a critique of the current $15/user/month model.\n"
    "5. Must NOT suggest building new product features — pricing analysis only.\n"
    "6. Output must be actionable for a GTM or pricing team."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (includes parallel SERP + Firecrawl + reddit tool calls)")

    result_state = pricing_graph.invoke(TEST_STATE)
    output = result_state.get("analysis_result", "")
    
    if not output:
        print("  ⚠ ERROR: No output returned from the graph!")
        sys.exit(1)

    print(f"  Output length: {len(output)} characters")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(GRAPH_NAME, output, CRITERIA)
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
