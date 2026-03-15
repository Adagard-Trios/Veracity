"""
Adjacent Node \u2014 Context extraction + Parallel data collection + LLM compilation.

Architecture:
    context_extractor: LLM defines the product's core boundaries and identifies its "job to be done".
    data_collector: Fires tools (Hacker News, SerpAPI) to find horizontal tech trends, 
                    neighboring products, and alternative startup solutions.
    compiler: Synthesizes findings into a "Market Collision & Blindspot Report".

Focus: What is coming from completely outside the user's category that could destroy them?
"""

import os
import requests
import concurrent.futures
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from src.llms.groqllm import GroqLLM
from src.utils.utils import query_chromadb, store_to_chromadb

load_dotenv()


# ==========================================================================
# Node 0: CONTEXT EXTRACTOR \u2014 Define the core boundaries
# ==========================================================================
def context_extractor(state) -> dict:
    """Extract the strict boundaries of the user's product to find what is *outside* it."""
    category = state.get("category", "Unknown")
    fetched_content = state.get("fetched_content", [])
    raw_text = "\\n\\n".join(fetched_content) if fetched_content else "(no content provided)"

    # Retrieve historical context
    historical_context = query_chromadb("adjacent_history", query=category, n_results=3)
    history_str = "\\n".join(historical_context) if historical_context else "(No historical data found)"

    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"You are a Disruptive Innovation Strategist. The user has provided an explanation "
        f"of their product in the '{category}' market.\\n\\n"
        f"---- HISTORICAL KNOWLEDGE ----\\n{history_str}\\n\\n"
        f"---- USER'S PRODUCT CONTENT ----\\n{raw_text[:10000]}\\n\\n"
        f"Extract the exact boundaries of their business to help us look *outside* of it:\\n"
        f"1. The Core 'Job to be Done' (What is the ultimate end-goal for the user?)\\n"
        f"2. Current Delivery Mechanism (How does the product solve it today?)\\n"
        f"3. Direct Category Definition (What specific SaaS/tool category do they put themselves in?)\\n"
        f"4. Search Queries:\\n"
        f"   - 2-3 Google queries for 'How to [Job to be Done] without [Current Delivery Mechanism]'\\n"
        f"   - 2-3 Hacker News queries for horizontal AI/Tech trends disrupting this '\\n"
        f"FOCUS ONLY on defining the box so we can look outside it."
    )

    extracted = response.content

    return {
        "extracted_context": extracted,
        "messages": [
            HumanMessage(content=f"Product boundaries extracted for '{category}':\\n\\n{extracted[:500]}...")
        ],
    }


# ==========================================================================
# Individual Tool Functions
# ==========================================================================
def _search_tech_trends(category: str) -> str:
    """Search Hacker News for underlying horizontal tech trends."""
    query = f"{category} OR AI disruption OR new infrastructure"
    url = "https://hn.algolia.com/api/v1/search"
    params = {"query": query, "tags": "story", "hitsPerPage": 5}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        hits = data.get("hits", [])
        if not hits:
            return "(No HN tech trends found for this category.)"
        
        results = []
        for hit in hits:
            title = hit.get("title", "")
            url = hit.get("url", "No URL")
            points = hit.get("points", 0)
            results.append(f"- {title} ({points} pts)\\n  Link: {url}")
        return "\\n\\n".join(results)
    except Exception as e:
        return f"(Error fetching HN tech trends: {e})"


def _search_adjacent_competitors(category: str) -> str:
    """Use SerpAPI to find neighboring products that might build this as a feature."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return "(Skipped: SERPAPI_API_KEY not set in .env)"
    
    query = f"alternative to {category} software OR top tools for {category}"
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": 5
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        organic_results = data.get("organic_results", [])
        
        if not organic_results:
            return "(No adjacent competitors found on SerpAPI.)"
            
        results = []
        for item in organic_results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            results.append(f"### {title}\\n{snippet}\\n{link}")
            
        return "\\n\\n".join(results)
    except requests.exceptions.HTTPError as he:
        # Avoid crashing on 401s if API key is invalid/exhausted
        return f"(SerpAPI Error: {he.response.status_code} - {he.response.text})"
    except Exception as e:
        return f"(Error searching adjacent competitors: {e})"


def _search_startup_threats(category: str) -> str:
    """Search HN or Serps for recent 'Show HN' or startup launches solving the same problem."""
    query = f"Show HN {category} OR launch {category}"
    url = "https://hn.algolia.com/api/v1/search_by_date"
    params = {"query": query, "tags": "story", "hitsPerPage": 5}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        hits = data.get("hits", [])
        if not hits:
            return "(No recent startup threats found on HN.)"
        
        results = []
        for hit in hits:
            title = hit.get("title", "")
            url = hit.get("url", "No URL")
            created = hit.get("created_at", "")
            results.append(f"- {title} (Launched: {created})\\n  Link: {url}")
        return "\\n\\n".join(results)
    except Exception as e:
        return f"(Error fetching startup threats: {e})"


# ==========================================================================
# Node 1: DATA COLLECTOR \u2014 Run tools in parallel
# ==========================================================================
def data_collector(state) -> dict:
    """Run adjacent market threat research tools in parallel."""
    category = state.get("category", "Unknown")
    extracted_context = state.get("extracted_context", "")

    search_category = category
    if extracted_context:
        search_category = f"{category} ({extracted_context[:100]})"

    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_search_tech_trends, search_category): "tech_trends",
            executor.submit(_search_adjacent_competitors, category): "adjacent_competitors",
            executor.submit(_search_startup_threats, category): "startup_threats",
        }

        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = f"(Error: {e})"

    tool_status = []
    for key, value in results.items():
        if value.startswith("(") and ("error" in value.lower() or "skipped" in value.lower() or "not set" in value.lower()):
            tool_status.append(f"  \u26a0 {key}: {value[:80]}")
        else:
            tool_status.append(f"  \u2713 {key}: {len(value)} chars collected")

    return {
        **results,
        "messages": [
            HumanMessage(content=(
                f"Data collection complete for '{category}' adjacent threats.\\n" +
                "\\n".join(tool_status)
            ))
        ],
    }


# ==========================================================================
# Node 2: COMPILER \u2014 Synthesize into Market Collision & Blindspot Report
# ==========================================================================
def compiler(state) -> dict:
    """Compile tool results into a final Market Collision Report."""
    category = state.get("category", "Unknown")
    extracted_context = state.get("extracted_context", "")

    tool_data = {
        "Horizontal Tech Trends": state.get("tech_trends", ""),
        "Neighboring Products": state.get("adjacent_competitors", ""),
        "Alternative Startup Solutions": state.get("startup_threats", ""),
    }

    sections = []
    for source, data in tool_data.items():
        truncated = data[:3000] if data else "(empty)"
        sections.append(f"### {source}\\n{truncated}")

    all_data = "\\n\\n".join(sections)

    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"You are a strict Growth Strategy and Disruption Expert. The user has provided "
        f"information defining the boundaries of their EXISTING product in the '{category}' market.\\n\\n"
        f"CRITICAL RULE: DO NOT tell the user how to optimize their current features. "
        f"Your ONLY job is to look OUTSIDE their category and show them the asymmetric threats and "
        f"market collisions they are not seeing.\\n\\n"
        f"## Background Context (The User's Product 'Box')\\n{extracted_context[:2000]}\\n\\n"
        f"## Gathered Market Threat Data (Outside the 'Box')\\n{all_data}\\n\\n"
        f"Produce a highly strategic 'Market Collision & Blindspot Report' answering:\\n\\n"
        f"### 1. The 'Job to be Done' Alternatives (Asymmetric Competition)\\n"
        f"- What other entirely different categories of products exist to solve the user's core problem?\\n"
        f"- Who is stealing the budget for this problem without being a direct feature-to-feature competitor?\\n\\n"
        f"### 2. The Feature Absorption Threat (The Godzilla Threat)\\n"
        f"- Which massive neighboring platform (like MS Teams, Notion, Salesforce, AWS) is most likely to build the user's entire product as a free toggle?\\n"
        f"- What is the evidence based on the gathered data?\\n\\n"
        f"### 3. The Unseen Horizontal Disruption\\n"
        f"- What new underlying technology (e.g., specific AI agent framework, open-source model) completely bypasses the need for the user's current delivery mechanism?\\n\\n"
        f"### 4. Strategic Defense & Pivot Vectors\\n"
        f"- Based on these threats, how should the user reposition or expand *today* to avoid getting steamrolled from the periphery?"
    )

    final_report = response.content

    # Store final adjacent report into ChromaDB
    store_to_chromadb(
        collection_name="adjacent_history",
        documents=[f"Category: {category}\\n\\n{final_report}"],
        metadatas=[{"category": category, "type": "market_collision_report"}],
    )

    return {
        "analysis_result": final_report,
        "messages": [
            AIMessage(content=final_report),
        ],
    }
