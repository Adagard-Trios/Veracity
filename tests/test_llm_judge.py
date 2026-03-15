"""
tests/test_llm_judge.py

LLM-as-Judge evaluation for the competitor agent pipeline.

These tests call the REAL competitor graph (Firecrawl + Groq LLM).
They consume ~9-12 Firecrawl credits and a few Groq tokens per run.

Skip in CI unless you want to spend credits:
    pytest tests/test_llm_judge.py -v -m llm_judge

Mark tests with the 'llm_judge' marker so they can be selectively run:
    pytest tests/ -m "not llm_judge"   # skip LLM judge tests
    pytest tests/ -m llm_judge         # ONLY run LLM judge tests

The judge LLM evaluates output quality on a rubric and returns a score 0-10.
A score >= 6 is considered a pass.
"""

import json
import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.llm_judge  # tag all tests in this module

PASS_THRESHOLD = 6  # out of 10


# ---------------------------------------------------------------------------
# Judge helper
# ---------------------------------------------------------------------------

def _llm_judge(rubric: str, data: str) -> dict:
    """
    Ask the Groq LLM to evaluate `data` against `rubric`.

    Returns:
        {"score": int (0-10), "reasoning": str, "passed": bool}
    """
    from src.llms.groqllm import GroqLLM
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = GroqLLM().get_llm(temperature=0)
    prompt = f"""You are an expert evaluator. Score the following output on a scale of 0 to 10 based on the rubric below.

RUBRIC:
{rubric}

OUTPUT TO EVALUATE:
{data}

Respond with ONLY valid JSON in this exact format (no preamble, no fences):
{{
  "score": <integer 0-10>,
  "reasoning": "<one sentence explaining the score>"
}}"""

    response = llm.invoke([
        SystemMessage(content="You are a strict output quality evaluator. Be critical."),
        HumanMessage(content=prompt),
    ])

    content = (
        response.content
        .strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    result = json.loads(content)
    result["passed"] = result["score"] >= PASS_THRESHOLD
    return result


# ---------------------------------------------------------------------------
# Integration test (real Firecrawl + Groq)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def competitor_graph_result():
    """Run the full competitor graph once — shared across all judge tests."""
    from src.graphs.competitor_graph import competitor_graph

    result = competitor_graph.invoke({
        "messages": [],
        "category": "AI SDR / cold email automation",
        "fetched_content": [
            "Apollo.io https://apollo.io is an AI sales platform. "
            "Instantly.ai https://instantly.ai automates cold email. "
            "Outreach.io https://outreach.io is a sales engagement platform."
        ],
        "competitor_tasks": [],
        "competitor_results": [],
        "analysis_result": "",
        "structured_output": {},
    })
    return result


# ---------------------------------------------------------------------------
# Judge Test 1 — Payload completeness
# ---------------------------------------------------------------------------

@pytest.mark.llm_judge
def test_judge_payload_completeness(competitor_graph_result):
    """
    Judge: Does the payload contain all required fields with non-empty values?
    Checks: competitors, feature_columns, category_summary, standard_features,
            overall_confidence > 0.
    """
    so = competitor_graph_result.get("structured_output", {})

    rubric = """
    Score the completeness of this CompetitivePayload JSON:
    - 10: All fields present and non-empty: competitors (>=2 entries), feature_columns (>=3),
          category_summary (>=1 sentence), standard_features (>=1), overall_confidence > 0.3
    - 7-9: Most fields present, minor gaps (e.g. missing_features is empty)
    - 4-6: Some fields missing or empty but core structure is there
    - 1-3: Payload is mostly empty or malformed
    - 0: No payload or all empty
    """
    verdict = _llm_judge(rubric, json.dumps(so, indent=2))
    print(f"\nCompleteness score: {verdict['score']}/10 — {verdict['reasoning']}")
    assert verdict["passed"], f"Completeness judge failed: {verdict['reasoning']}"


# ---------------------------------------------------------------------------
# Judge Test 2 — Competitor data quality
# ---------------------------------------------------------------------------

@pytest.mark.llm_judge
def test_judge_competitor_data_quality(competitor_graph_result):
    """
    Judge: Is the competitor data accurate and specific (not generic placeholders)?
    """
    so = competitor_graph_result.get("structured_output", {})
    competitors = so.get("competitors", [])

    rubric = """
    Score the QUALITY and SPECIFICITY of competitor data in this list:
    - 10: Each competitor has a real tagline, 3+ features with snake_case keys,
          a real pricing_tier (not "not shown"), and at least one source URL
    - 7-9: Most competitors have real data, 1-2 have thin detail
    - 4-6: Data is generic or vague (e.g. features are just ["feature1"])
    - 1-3: Competitor names present but almost no real data
    - 0: Empty or completely fabricated/nonsensical
    """
    verdict = _llm_judge(rubric, json.dumps(competitors, indent=2))
    print(f"\nData quality score: {verdict['score']}/10 — {verdict['reasoning']}")
    assert verdict["passed"], f"Data quality judge failed: {verdict['reasoning']}"


# ---------------------------------------------------------------------------
# Judge Test 3 — Category summary quality
# ---------------------------------------------------------------------------

@pytest.mark.llm_judge
def test_judge_category_summary(competitor_graph_result):
    """
    Judge: Is the category_summary a useful, specific strategic insight?
    """
    so = competitor_graph_result.get("structured_output", {})
    summary = so.get("category_summary", "")

    rubric = """
    Score this competitive landscape summary for strategic value:
    - 10: 2+ sentences, mentions actual market trends or competitive dynamics,
          not generic, specific to AI SDR / cold email category
    - 7-9: Good insight but slightly vague or only 1 sentence
    - 4-6: Generic or could apply to any software category
    - 1-3: Barely says anything useful
    - 0: Empty or error message
    """
    verdict = _llm_judge(rubric, summary)
    print(f"\nSummary quality score: {verdict['score']}/10 — {verdict['reasoning']}")
    assert verdict["passed"], f"Summary judge failed: {verdict['reasoning']}"


# ---------------------------------------------------------------------------
# Judge Test 4 — Confidence calibration
# ---------------------------------------------------------------------------

@pytest.mark.llm_judge
def test_judge_confidence_calibration(competitor_graph_result):
    """
    Judge: Are confidence scores realistic (not all 0.0 or all 1.0)?
    """
    so = competitor_graph_result.get("structured_output", {})

    # Collect all confidence scores from feature entries
    all_confidences = []
    for comp in so.get("competitors", []):
        for feat_val in comp.get("features", {}).values():
            if isinstance(feat_val, dict):
                all_confidences.append(feat_val.get("confidence", 0))
    overall = so.get("overall_confidence", 0)
    all_confidences.append(overall)

    rubric = f"""
    Evaluate whether this list of confidence scores is well-calibrated:
    Scores: {all_confidences}
    Overall confidence: {overall}

    - 10: Scores vary between 0.3 and 0.95, not all the same value, overall in 0.5-0.9 range
    - 7-9: Mostly reasonable but slightly over- or under-confident
    - 4-6: All scores identical or extreme (all 0.0 or all 1.0)
    - 1-3: Confidence scores present but nonsensical
    - 0: No confidence scores at all
    """
    verdict = _llm_judge(rubric, str(all_confidences))
    print(f"\nConfidence calibration score: {verdict['score']}/10 — {verdict['reasoning']}")
    assert verdict["passed"], f"Confidence calibration judge failed: {verdict['reasoning']}"


# ---------------------------------------------------------------------------
# Judge Test 5 — Feature matrix consistency
# ---------------------------------------------------------------------------

@pytest.mark.llm_judge
def test_judge_feature_matrix_consistency(competitor_graph_result):
    """
    Judge: Are feature_columns consistent with the features listed in competitors?
    All feature keys in competitors should appear in feature_columns and vice versa.
    """
    so = competitor_graph_result.get("structured_output", {})
    feature_columns = set(so.get("feature_columns", []))
    all_comp_features = set()
    for comp in so.get("competitors", []):
        all_comp_features.update(comp.get("features", {}).keys())

    data = {
        "feature_columns": list(feature_columns),
        "all_competitor_feature_keys": list(all_comp_features),
        "only_in_columns": list(feature_columns - all_comp_features),
        "only_in_competitors": list(all_comp_features - feature_columns),
    }

    rubric = """
    Score the consistency of feature_columns vs the actual feature keys in competitors:
    - 10: feature_columns and competitor feature keys are identical sets
    - 7-9: Minor mismatches (1-2 extra or missing columns)
    - 4-6: Several features appear only in one place
    - 1-3: Significant mismatch
    - 0: No features at all
    """
    verdict = _llm_judge(rubric, json.dumps(data, indent=2))
    print(f"\nFeature matrix consistency score: {verdict['score']}/10 — {verdict['reasoning']}")
    assert verdict["passed"], f"Feature consistency judge failed: {verdict['reasoning']}"
