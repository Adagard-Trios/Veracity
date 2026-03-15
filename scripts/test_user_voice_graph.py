"""
test_user_voice_graph.py — LLM-as-Judge evaluation for the User Voice (VOC) Graph.

Run from the project root:
    python scripts/test_user_voice_graph.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import evaluate_with_llm_judge, print_header, print_result, save_test_result
from src.graphs.user_voice_graph import user_voice_graph

GRAPH_NAME = "User Voice (VOC) Graph"
TEST_STATE = {
    "messages": [],
    "category": "Task Management SaaS for Creative Agencies",
    "fetched_content": [
        "Our product is a project management platform built for creative agencies. "
        "We have Kanban boards, time-tracking, client approval portals, and asset management. "
        "We charge $15/user/month. Main competitors are Asana, Monday.com, and ClickUp."
    ],
    "extracted_context": "",
    "reddit_feedback": "",
    "hn_feedback": "",
    "review_site_snippets": "",
    "scraped_reviews": "",
    "competitor_messaging": "",
    "analysis_result": "",
}

CRITERIA = (
    "1. CRITICAL: Must NEVER suggest building new product features. This is a voice-of-customer / messaging analysis ONLY.\n"
    "2. Must identify the 'Sea of Sameness' — the buzzwords and cliché language all competitors use.\n"
    "3. Must surface exact user vocabularies and pain-point phrases from community data (Reddit, reviews, HN).\n"
    "4. Must provide at least 3 specific messaging hooks or copywriting angles based on real user language.\n"
    "5. Must identify emotional triggers or friction moments from real users.\n"
    "6. Must be grounded in data from actual sources — not made-up user quotes."
)

if __name__ == "__main__":
    print_header(f"LLM Judge Test: {GRAPH_NAME}")
    print("  Invoking graph... (includes parallel review + community scraping)")

    result_state = user_voice_graph.invoke(TEST_STATE)
    output = result_state.get("analysis_result", "")
    
    if not output:
        print("  ⚠ ERROR: No output returned from the graph!")
        sys.exit(1)

    print(f"  Output length: {len(output)} characters")
    print("  Sending to LLM judge...")

    evaluation = evaluate_with_llm_judge(GRAPH_NAME, output, CRITERIA)
    filepath = save_test_result(GRAPH_NAME, evaluation, output)
    print_result(evaluation, filepath)
