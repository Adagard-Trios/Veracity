"""
llm_judge.py — Shared LLM-as-Judge scoring utility.

All individual test files import this module to evaluate agent outputs.

Key improvements over v1:
- Increased judge snippet from 3000 → 6000 chars for richer evaluation
- Fixed Win/Loss file-path bug (slash in name → Windows path error)
- Robust multi-line score/verdict parser using regex
- Score-based verdict recomputation as a safety net
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llms.groqllm import GroqLLM

# -----------------------------------------------------------------
# Config
# -----------------------------------------------------------------
RESULTS_DIR = Path(__file__).parent.parent / "test_results"
PASS_THRESHOLD = 7  # Score of 7+ is a PASS


def get_results_dir():
    RESULTS_DIR.mkdir(exist_ok=True)
    return RESULTS_DIR


def evaluate_with_llm_judge(
    graph_name: str,
    output: str,
    criteria: str,
    extra_context: Optional[str] = None,
) -> dict:
    """
    Use the LLM as an impartial judge to score an agent output.

    Returns a dict with:
        - score (int 1-10)
        - verdict ("PASS" | "FAIL")
        - strengths (str)
        - weaknesses (str)
        - full_evaluation (str)
    """
    llm = GroqLLM().get_llm(temperature=0.0)

    extra = f"\n### Additional Context\n{extra_context}\n" if extra_context else ""

    # Pass up to 6000 chars of agent output so the judge has enough context
    prompt = (
        f"You are an expert LLM-as-a-Judge evaluating a Growth Intelligence AI agent.\n"
        f"IMPORTANT: Be rigorous and unbiased. Only award high scores when the output genuinely meets the criteria.\n\n"
        f"### Agent Being Evaluated: `{graph_name}`\n\n"
        f"### Evaluation Criteria (must check each one)\n{criteria}\n"
        f"{extra}"
        f"\n### Agent Output to Evaluate\n"
        f"{'='*60}\n{output[:6000]}\n{'='*60}\n\n"
        f"### Your Response (MUST follow this exact format, one label per line)\n"
        f"STRENGTHS: <what the agent did well>\n"
        f"WEAKNESSES: <what it missed, hallucinated, or did poorly>\n"
        f"SCORE: <integer between 1 and 10>\n"
        f"VERDICT: <PASS if SCORE >= {PASS_THRESHOLD}, else FAIL>\n"
    )

    response = llm.invoke(prompt)
    raw = response.content.strip()

    # ---- Robust parser ----
    score = 5
    verdict = "FAIL"
    strengths = ""
    weaknesses = ""

    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("SCORE:"):
            nums = re.findall(r"\b(\d{1,2})\b", stripped)
            if nums:
                score = min(10, max(1, int(nums[0])))
        elif stripped.upper().startswith("VERDICT:"):
            verdict = "PASS" if "PASS" in stripped.upper() else "FAIL"
        elif stripped.upper().startswith("STRENGTHS:"):
            strengths = stripped[len("STRENGTHS:"):].strip()
        elif stripped.upper().startswith("WEAKNESSES:"):
            weaknesses = stripped[len("WEAKNESSES:"):].strip()

    # Safety net: recompute verdict from score
    verdict = "PASS" if score >= PASS_THRESHOLD else "FAIL"

    return {
        "graph_name": graph_name,
        "score": score,
        "verdict": verdict,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "full_evaluation": raw,
    }


def save_test_result(graph_name: str, result: dict, output: str):
    """Save full test result to JSON in test_results/"""
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize filename — remove chars illegal on Windows paths (/ \ : * ? " < > |)
    safe_name = re.sub(r'[/\\:*?"<>|]', "-", graph_name).replace(" ", "_").lower()
    filepath = RESULTS_DIR / f"{safe_name}_{timestamp}.json"

    payload = {
        "graph_name": graph_name,
        "timestamp": datetime.now().isoformat(),
        "agent_output_snippet": output[:4000],
        "evaluation": result,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return str(filepath)


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(result: dict, filepath: str):
    verdict_color = "\033[92m" if result["verdict"] == "PASS" else "\033[91m"
    reset = "\033[0m"
    print(f"\n  Score:    {result['score']}/10")
    print(f"  Verdict:  {verdict_color}{result['verdict']}{reset}")
    if result.get("strengths"):
        print(f"  Strength: {result['strengths'][:150]}")
    if result.get("weaknesses"):
        print(f"  Weakness: {result['weaknesses'][:150]}")
    print(f"  Saved:    {filepath}")
