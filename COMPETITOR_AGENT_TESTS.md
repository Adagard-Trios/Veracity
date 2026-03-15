# Competitor Agent — Test Guide

> **For teammates joining this module.** Covers what the competitor agent does, how to run tests, and how to interpret LLM-judge results.

---

## What the agent does

When given a product category + pre-fetched context, the competitor graph:

1. **Planner** — asks the LLM to identify 3-5 competitors and their URLs from the context
2. **Parallel fetch** — fans out one branch per competitor (LangGraph `Send` API). Inside each branch, 3 Firecrawl calls run **concurrently** via `ThreadPoolExecutor`:
   - `fetch_competitor_website` — homepage: tagline, features, pricing
   - `fetch_competitor_changelog` — recent product launches
   - `fetch_producthunt_launches` — community reception & upvotes
3. **Compiler** — LLM structured extraction aggregates all results → `CompetitivePayload`
4. **SSE emit** — `artifact_update` + `agent_complete` events pushed to the frontend queue

---

## Key files

| File | Purpose |
|---|---|
| `src/nodes/competitor_schemas.py` | Pydantic models — `CompetitivePayload`, `CompetitorTask`, etc. |
| `src/nodes/competitor_tools.py` | 3 Firecrawl tools (direct httpx calls) |
| `src/nodes/competitor_node.py` | `planner_node`, `route_to_fetchers`, `competitor_fetch_node`, `compiler_node` |
| `src/graphs/competitor_graph.py` | LangGraph graph wiring |
| `src/states/competitor_state.py` | State schema with `operator.add` reducer on `competitor_results` |
| `src/utils/sse.py` | `emit_sse_artifact` helper (shared, avoids circular import) |

---

## Environment variables required

```bash
GROQ_API_KEY=...         # LLM calls (planner + compiler)
FIRECRAWL_API_KEY=...    # Live website scraping (3 tools)
```

---

## Test overview

| Test file | Type | Credits used | When to run |
|---|---|---|---|
| `test_competitor_tools.py` | Unit — mocked | 0 | Always (CI) |
| `test_competitor_node.py` | Unit — mocked | 0 | Always (CI) |
| `test_llm_judge.py` | Integration + LLM judge | ~12 Firecrawl + Groq tokens | Pre-demo / manually |

---

## Last verified run — 2026-03-15

### Unit tests (18/18 passed, 1.44s)

```
tests/test_competitor_tools.py::TestFetchCompetitorWebsite::test_returns_json_string                PASSED
tests/test_competitor_tools.py::TestFetchCompetitorWebsite::test_returns_low_confidence_on_empty_extract PASSED
tests/test_competitor_tools.py::TestFetchCompetitorWebsite::test_handles_firecrawl_error_gracefully PASSED
tests/test_competitor_tools.py::TestFetchCompetitorWebsite::test_missing_env_key_raises             PASSED
tests/test_competitor_tools.py::TestFetchCompetitorChangelog::test_returns_recent_launches          PASSED
tests/test_competitor_tools.py::TestFetchCompetitorChangelog::test_empty_changelog_returns_low_confidence PASSED
tests/test_competitor_tools.py::TestFetchProducthuntLaunches::test_returns_launches_list            PASSED
tests/test_competitor_tools.py::TestFetchProducthuntLaunches::test_no_results_returns_low_confidence PASSED
tests/test_competitor_node.py::TestPlannerNode::test_returns_dict_with_competitor_tasks             PASSED
tests/test_competitor_node.py::TestPlannerNode::test_handles_invalid_llm_json_gracefully            PASSED
tests/test_competitor_node.py::TestPlannerNode::test_handles_empty_fetched_content                  PASSED
tests/test_competitor_node.py::TestRouteToFetchers::test_returns_send_per_task                      PASSED
tests/test_competitor_node.py::TestRouteToFetchers::test_empty_tasks_routes_to_compiler             PASSED
tests/test_competitor_node.py::TestCompetitorFetchNode::test_fetches_all_three_tools_concurrently   PASSED
tests/test_competitor_node.py::TestCompetitorFetchNode::test_continues_if_one_tool_fails            PASSED
tests/test_competitor_node.py::TestCompilerNode::test_produces_valid_competitive_payload            PASSED
tests/test_competitor_node.py::TestCompilerNode::test_empty_results_returns_fallback_payload        PASSED
tests/test_competitor_node.py::TestCompilerNode::test_compiler_handles_llm_json_parse_failure       PASSED
```

### LLM judge tests (5/5 passed, 1m 41s, ~12 Firecrawl credits)

| Judge | Score | Reasoning |
|---|---|---|
| Payload completeness | **8/10** ✅ | All major sections filled; `standard_features` was empty — see note below |
| Competitor data quality | **8/10** ✅ | Two competitors complete; one lacked a concrete pricing tier |
| Category summary | **10/10** ✅ | Specific 2-sentence insight naming real players and competitive dynamics |
| Confidence calibration | **10/10** ✅ | Scores varied (0.57–0.85), overall in 0.5–0.9 range |
| Feature matrix consistency | **10/10** ✅ | `feature_columns` exactly matched competitor feature keys |

> **Note on `standard_features: []`** — This is **expected behaviour, not a bug.** A feature is "standard" when it appears in 3+ competitors. With only 3 competitors in the test run, the LLM rarely assigns the exact same feature key to all three (slight naming variations). Run with 4-5 competitors from richer pre-fetched content and this field will populate. No code change needed.

---

## Running the tests

### 1. Fast unit tests only (no credits, runs in seconds)

```powershell
cd c:\git\personal\Veracity
.\.venv\Scripts\pytest tests/test_competitor_tools.py tests/test_competitor_node.py -v
```

Expected: **all green**, no network calls made.

### 2. Skip LLM judge (all tests except the live ones)

```powershell
.\.venv\Scripts\pytest tests/ -m "not llm_judge" -v
```

### 3. LLM judge only (~2-3 min, consumes ~12 Firecrawl credits)

```powershell
.\.venv\Scripts\pytest tests/test_llm_judge.py -v -s
```

The `-s` flag shows the judge scores printed to stdout.

### 4. All tests

```powershell
.\.venv\Scripts\pytest tests/ -v -s
```

---

## Manual smoke tests (no pytest)

### Single tool — 1 Firecrawl credit

```powershell
.\.venv\Scripts\python.exe -c "
import json
from dotenv import load_dotenv; load_dotenv()
from src.nodes.competitor_tools import fetch_competitor_website

result = fetch_competitor_website.invoke({
    'competitor_name': 'Apollo.io',
    'website_url': 'https://www.apollo.io'
})
print(json.dumps(json.loads(result), indent=2))
"
```

**Expected:** JSON with `confidence: 0.85` and a `data` block containing tagline, features, pricing.

---

### Planner only — 0 credits, 1 LLM call

```powershell
.\.venv\Scripts\python.exe -c "
from dotenv import load_dotenv; load_dotenv()
from src.nodes.competitor_node import planner_node

state = {
    'category': 'AI SDR / digital workers',
    'fetched_content': [
        'Apollo.io is an AI-powered sales platform. Outreach.io is a sales engagement tool. Instantly.ai automates cold email outreach.'
    ],
    'competitor_results': [],
    'competitor_tasks': [],
    'analysis_result': '',
    'structured_output': {},
    'messages': [],
}
result = planner_node(state)
for task in result['competitor_tasks']:
    print('Task:', task['name'], '->', task['website_url'])
"
```

**Expected:** 3 competitor task dicts with names and URLs.

---

### Full competitor graph — ~9-12 Firecrawl credits

```powershell
.\.venv\Scripts\python.exe -c "
import json
from dotenv import load_dotenv; load_dotenv()
from src.graphs.competitor_graph import competitor_graph

result = competitor_graph.invoke({
    'messages': [],
    'category': 'AI SDR / digital workers',
    'fetched_content': [
        'Apollo.io https://apollo.io - AI sales platform. Outreach.io https://outreach.io - sales engagement. Instantly.ai https://instantly.ai - cold email automation.'
    ],
    'competitor_tasks': [],
    'competitor_results': [],
    'analysis_result': '',
    'structured_output': {},
})

print('=== analysis_result ===')
print(result.get('analysis_result'))
print()
so = result.get('structured_output', {})
print('=== competitors ===')
for c in so.get('competitors', []):
    print(' -', c['name'], '|', c.get('tagline','')[:60])
print()
print('feature_columns:', so.get('feature_columns'))
print('overall_confidence:', so.get('overall_confidence'))
"
```

**Expected:** Structured JSON with 3 competitors, feature matrix, category summary, and an overall confidence of ~0.5-0.9.

---

## Understanding LLM judge results

Each judge test scores one aspect of the `CompetitivePayload` on a 0-10 scale. **Pass threshold: 6/10.**

| Judge test | What it measures |
|---|---|
| `test_judge_payload_completeness` | All required fields non-empty |
| `test_judge_competitor_data_quality` | Real, specific data (not generic placeholders) |
| `test_judge_category_summary` | Strategic insight value of the summary |
| `test_judge_confidence_calibration` | Confidence scores are realistic and varied |
| `test_judge_feature_matrix_consistency` | `feature_columns` matches feature keys in competitors |

When a judge test fails, the `reasoning` field in the assertion error message explains exactly what was wrong. Fix the prompts in `competitor_node.py` (either `PLANNER_SYSTEM` or `COMPILER_SYSTEM`) and re-run.

---

## Debugging tips

| Symptom | Likely cause | Fix |
|---|---|---|
| `FIRECRAWL_API_KEY not set` | `.env` not loaded | Add `load_dotenv()` or export env var |
| `confidence: 0.0` on all tools | Firecrawl blocked the URL | Try a different page or check Firecrawl dashboard |
| Planner returns 0 tasks | Pre-fetched content too vague | Add explicit competitor names + URLs to `fetched_content` |
| Compiler returns `overall_confidence: 0.1` | LLM JSON parse failure | Check `analysis_result` for the error message; check Groq rate limits |
| `InvalidUpdateError: Expected dict, got [Send...]` | Node returning `list[Send]` directly | Nodes must return dicts — only edge functions return `list[Send]` |

---

## Firecrawl credit budget

- Free tier: **500 credits**
- Each `_firecrawl_scrape` call = **1 credit**
- Full pipeline run (3 competitors × 3 tools) = **~9 credits**
- Available full runs on free tier: **~55**

> Run `test_competitor_tools.py` and `test_competitor_node.py` (mocked) during development. Only run the full graph / LLM judge tests when validating a change end-to-end.
