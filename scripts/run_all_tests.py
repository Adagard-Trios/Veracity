"""
run_all_tests.py — Master test runner for all Veracity graph LLM-as-Judge evaluations.

Runs every graph test, records results in test_results/, and prints a score summary.

Usage:
    python scripts/run_all_tests.py             # run all tests
    python scripts/run_all_tests.py --graph pricing    # run only pricing test
    python scripts/run_all_tests.py --skip-full       # skip the slow full veracity graph test

Available --graph values: adjacent, competitor, market_trend, pricing, user_voice, win_loss, veracity
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.llm_judge import (
    evaluate_with_llm_judge, save_test_result, print_header, PASS_THRESHOLD, RESULTS_DIR
)

# -------------------------------------------------------------------------
# Individual test imports
# -------------------------------------------------------------------------

def run_adjacent():
    from src.graphs.adjacent_graph import adjacent_graph
    state = {
        "messages": [], "category": "Task Management SaaS for Creative Agencies",
        "fetched_content": ["Our product is a PM platform for agencies. Competitors: Asana, Monday.com, ClickUp."],
    }
    from scripts.test_adjacent_graph import CRITERIA
    r = adjacent_graph.invoke(state)
    return r.get("analysis_result", ""), CRITERIA


def run_competitor():
    from src.graphs.competitor_graph import competitor_graph
    state = {
        "messages": [], "category": "Task Management SaaS for Creative Agencies",
        "fetched_content": ["Our product is a PM platform for agencies. Competitors: Asana, Monday.com, ClickUp."],
        "competitor_tasks": [], "competitor_results": [], "analysis_result": "", "structured_output": {},
    }
    from scripts.test_competitor_graph import CRITERIA
    r = competitor_graph.invoke(state)
    return r.get("analysis_result", ""), CRITERIA


def run_market_trend():
    from src.graphs.marketing_trend_graph import marketing_trend_graph
    state = {
        "messages": [], "brand": "AgencyFlow", "category": "Task Management SaaS for Creative Agencies",
        "query": "What are the biggest trends in how agencies manage creative projects?",
        "sources": [], "raw_data": [], "analysis_tasks": [], "analysis_results": [], "analysis_report": "",
    }
    from scripts.test_market_trend_graph import CRITERIA
    r = marketing_trend_graph.invoke(state)
    return r.get("analysis_report", ""), CRITERIA


def run_pricing():
    from src.graphs.pricing_graph import pricing_graph
    state = {
        "messages": [], "category": "Task Management SaaS for Creative Agencies",
        "fetched_content": ["Our product is a PM platform for agencies, $15/user/month. vs Asana, Monday, ClickUp."],
        "extracted_context": "", "serp_results": "", "meta_ad_results": "", "scraped_pricing_pages": "",
        "reddit_results": "", "hn_results": "", "linkedin_ad_results": "", "content_analysis": "", "analysis_result": "",
    }
    from scripts.test_pricing_graph import CRITERIA
    r = pricing_graph.invoke(state)
    return r.get("analysis_result", ""), CRITERIA


def run_user_voice():
    from src.graphs.user_voice_graph import user_voice_graph
    state = {
        "messages": [], "category": "Task Management SaaS for Creative Agencies",
        "fetched_content": ["Our product is a PM platform for agencies, $15/user/month."],
        "extracted_context": "", "reddit_feedback": "", "hn_feedback": "",
        "review_site_snippets": "", "scraped_reviews": "", "competitor_messaging": "", "analysis_result": "",
    }
    from scripts.test_user_voice_graph import CRITERIA
    r = user_voice_graph.invoke(state)
    return r.get("analysis_result", ""), CRITERIA


def run_win_loss():
    from src.graphs.win_loss_graph import win_loss_graph
    state = {
        "messages": [], "brand": "AgencyFlow", "category": "Task Management SaaS for Creative Agencies",
        "competitors": ["Asana", "Monday.com", "ClickUp"],
        "query": "Why are we losing deals to Monday.com in the mid-market?",
        "sources": [], "raw_signals": [], "extraction_tasks": [], "extracted_signals": [],
        "signal_matrix": "", "win_loss_report": "",
    }
    from scripts.test_win_loss_graph import CRITERIA
    r = win_loss_graph.invoke(state)
    return r.get("win_loss_report", "") + "\n\n" + r.get("signal_matrix", ""), CRITERIA


GRAPH_TESTS = {
    "adjacent":     ("Adjacent Market Graph",        run_adjacent),
    "competitor":   ("Competitor Analysis Graph",    run_competitor),
    "market_trend": ("Market Trend Graph",           run_market_trend),
    "pricing":      ("Pricing Analysis Graph",       run_pricing),
    "user_voice":   ("User Voice (VOC) Graph",       run_user_voice),
    "win_loss":     ("Win/Loss Intelligence Graph",  run_win_loss),
}


def print_summary(results: list):
    print("\n\n" + "=" * 65)
    print("  VERACITY AI — LLM JUDGE TEST SUMMARY")
    print(f"  Ran at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")

    print(f"  {'Graph':<35} {'Score':>6} {'Verdict':>8}")
    print(f"  {'-'*35} {'-'*6} {'-'*8}")
    for r in results:
        verdict_marker = "✅" if r["verdict"] == "PASS" else "❌"
        print(f"  {r['graph']:<35} {r['score']:>5}/10 {verdict_marker} {r['verdict']:>6}")

    print("=" * 65)
    pct = (passed / total * 100) if total else 0
    print(f"  Result: {passed}/{total} tests passed ({pct:.0f}%)")
    if passed == total:
        print("  🎉 ALL TESTS PASSED!")
    else:
        print("  ⚠  Some tests failed — review test_results/ for details.")
    print("=" * 65)


def save_run_summary(results: list):
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RESULTS_DIR / f"summary_{timestamp}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results),
        "passed": sum(1 for r in results if r["verdict"] == "PASS"),
        "results": results,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\n  Full summary saved to: {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all Veracity LLM Judge tests.")
    parser.add_argument(
        "--graph", choices=list(GRAPH_TESTS.keys()) + ["all"],
        default="all", help="Which graph to test"
    )
    args = parser.parse_args()

    tests_to_run = GRAPH_TESTS if args.graph == "all" else {args.graph: GRAPH_TESTS[args.graph]}

    all_results = []

    for key, (graph_name, run_fn) in tests_to_run.items():
        print_header(f"Testing: {graph_name}")
        try:
            print(f"  Invoking graph...")
            output, criteria = run_fn()
            if not output:
                print("  ⚠ No output returned. Skipping evaluation.")
                all_results.append({"graph": graph_name, "score": 0, "verdict": "FAIL", "error": "Empty output"})
                continue

            print(f"  Output length: {len(output)} chars. Sending to LLM judge...")
            evaluation = evaluate_with_llm_judge(graph_name, output, criteria)
            filepath = save_test_result(graph_name, evaluation, output)

            print(f"\n  Score:   {evaluation['score']}/10")
            marker = "✅ PASS" if evaluation['verdict'] == "PASS" else "❌ FAIL"
            print(f"  Verdict: {marker}")
            print(f"  Saved:   {filepath}")

            all_results.append({
                "graph": graph_name,
                "score": evaluation["score"],
                "verdict": evaluation["verdict"],
                "filepath": filepath
            })

        except Exception as e:
            print(f"  ✗ EXCEPTION: {e}")
            all_results.append({"graph": graph_name, "score": 0, "verdict": "ERROR", "error": str(e)})

    print_summary(all_results)
    save_run_summary(all_results)
