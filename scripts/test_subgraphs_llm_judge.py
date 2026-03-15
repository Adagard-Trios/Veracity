"""
LLM-as-a-Judge test script for Veracity Subgraphs.

This script runs the completed subgraphs (Pricing, User Voice, Adjacent)
with dummy input data and uses GroqLLM as an impartial judge to score
the outputs based on specific criteria for each graph.
"""

import os
import sys
import argparse
from termcolor import colored

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graphs.pricing_graph import pricing_graph
from src.graphs.user_voice_graph import user_voice_graph
from src.graphs.adjacent_graph import adjacent_graph
from src.llms.groqllm import GroqLLM


# ==============================================================================
# Test Data
# ==============================================================================
TEST_CATEGORY = "Task Management for Agencies"
TEST_CONTENT = [
    "Our product is a task management tool built specifically for creative agencies. "
    "We have Kanban boards, integrated time tracking, and client approval portals. "
    "We cost $15/user/month. We compete with Asana, Monday.com, and ClickUp, but we "
    "focus solely on the agency workflow because we were tired of generic tools that "
    "required too much setup. Our tagline is 'Manage your creative workflow, not your software'."
]

def get_initial_state(category: str, content: list[str]) -> dict:
    return {
        "messages": [],
        "category": category,
        "fetched_content": content,
    }


# ==============================================================================
# LLM Judge Configuration
# ==============================================================================
def evaluate_with_llm(graph_name: str, output: str, criteria: str) -> str:
    """Use the LLM to judge the output based on given criteria."""
    llm = GroqLLM().get_llm(temperature=0.0)
    
    prompt = (
        f"You are an impartial, expert 'LLM-as-a-Judge'. You evaluate AI agent outputs.\n\n"
        f"## TASK DESCRIPTION\n"
        f"You are evaluating the output of the '{graph_name}' agent.\n\n"
        f"## EVALUATION CRITERIA\n"
        f"{criteria}\n\n"
        f"## AGENT OUTPUT TO EVALUATE\n"
        f"=========================================\n"
        f"{output}\n"
        f"=========================================\n\n"
        f"## YOUR RESPONSE FORMAT\n"
        f"1. **Strengths**: What did it do well based on the criteria?\n"
        f"2. **Weaknesses**: Where did it fail or hallucinate?\n"
        f"3. **Score**: Provide a final score (1-10) where 10 is absolute perfection complying perfectly with criteria.\n"
        f"4. **Verdict**: PASS or FAIL (Requires an 8 or above to pass)."
    )
    
    response = llm.invoke(prompt)
    return response.content


# ==============================================================================
# Graph-Specific Test Runners
# ==============================================================================
def test_pricing_graph():
    print(colored("\n" + "="*50, "cyan"))
    print(colored("Running Tests: PRICING GRAPH", "cyan", attrs=["bold"]))
    print(colored("="*50, "cyan"))
    
    state = get_initial_state(TEST_CATEGORY, TEST_CONTENT)
    print("Invoking graph... (this may take a minute due to parallel scraping)")
    result = pricing_graph.invoke(state)
    
    output = result.get("analysis_result", "")
    print(colored(f"\n--- Output Snippet ---\n{output[:500]}...\n", "dark_grey"))
    
    criteria = (
        "- Must extract different pricing models used in the market.\n"
        "- Must analyze willingness-to-pay (WTP) based on Reddit/HN discussions.\n"
        "- Must provide competitive pricing benchmarks.\n"
        "- Must provide strategic recommendations on pricing."
    )
    
    print(colored("Evaluating with LLM Judge...", "yellow"))
    evaluation = evaluate_with_llm("Pricing Graph", output, criteria)
    print(colored("\n--- Judge Evaluation ---\n", "magenta"))
    print(evaluation)


def test_user_voice_graph():
    print(colored("\n" + "="*50, "cyan"))
    print(colored("Running Tests: USER VOICE GRAPH", "cyan", attrs=["bold"]))
    print(colored("="*50, "cyan"))
    
    state = get_initial_state(TEST_CATEGORY, TEST_CONTENT)
    print("Invoking graph... (this may take a minute due to parallel scraping)")
    result = user_voice_graph.invoke(state)
    
    output = result.get("analysis_result", "")
    print(colored(f"\n--- Output Snippet ---\n{output[:500]}...\n", "dark_grey"))
    
    criteria = (
        "- MUST NOT suggest features or product roadmap items under any circumstances.\n"
        "- Must identify the 'Sea of Sameness' (jargon competitors use).\n"
        "- Must identify strict real user vocabulary from frustrated users.\n"
        "- Must provide 3-4 specific messaging/copywriting hooks on how to talk about existing features."
    )
    
    print(colored("Evaluating with LLM Judge...", "yellow"))
    evaluation = evaluate_with_llm("User Voice Graph", output, criteria)
    print(colored("\n--- Judge Evaluation ---\n", "magenta"))
    print(evaluation)


def test_adjacent_graph():
    print(colored("\n" + "="*50, "cyan"))
    print(colored("Running Tests: ADJACENT GRAPH", "cyan", attrs=["bold"]))
    print(colored("="*50, "cyan"))
    
    state = get_initial_state(TEST_CATEGORY, TEST_CONTENT)
    print("Invoking graph... (this may take a minute due to parallel scraping)")
    result = adjacent_graph.invoke(state)
    
    output = result.get("analysis_result", "")
    print(colored(f"\n--- Output Snippet ---\n{output[:500]}...\n", "dark_grey"))
    
    criteria = (
        "- MUST NOT focus on optimizing current direct features.\n"
        "- Must identify entirely different 'Job to be Done' alternatives.\n"
        "- Must discuss the 'Feature Absorption Threat' (e.g., MS Teams/Notion building this as a feature).\n"
        "- Must identify an unseen horizontal tech disruption (e.g., AI agents).\n"
        "- Must provide strategic defense/pivot vectors against asymmetric threats."
    )
    
    print(colored("Evaluating with LLM Judge...", "yellow"))
    evaluation = evaluate_with_llm("Adjacent Market Graph", output, criteria)
    print(colored("\n--- Judge Evaluation ---\n", "magenta"))
    print(evaluation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Veracity subgraphs with LLM judging.")
    parser.add_argument("--graph", choices=["all", "pricing", "user_voice", "adjacent"], default="all",
                        help="Which graph to test.")
    args = parser.parse_args()
    
    # Ensure dependencies are available (termcolor used for nice CLI output)
    try:
        import termcolor
    except ImportError:
        print("Installing test dependencies (termcolor)...")
        os.system("pip install termcolor")
        print("\n")

    if args.graph in ["all", "pricing"]:
        test_pricing_graph()
    if args.graph in ["all", "user_voice"]:
        test_user_voice_graph()
    if args.graph in ["all", "adjacent"]:
        test_adjacent_graph()
    
    print(colored("\n==== ALL TESTS COMPLETED ====", "green", attrs=["bold"]))
