"""
Pricing Node — Context extraction + Parallel data collection + LLM compilation.

Architecture:
    context_extractor: LLM extracts structured context from raw input paragraphs.
    data_collector: Fires ALL tools once in parallel using the extracted context.
    compiler: LLM reads all tool results and produces a synthesized pricing analysis.

Tools used: SerpAPI, Meta Ad Library, Firecrawl, Reddit, HN Algolia, LinkedIn Ad Library.
"""

import os
import json
import requests
import concurrent.futures
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from src.llms.groqllm import GroqLLM
from src.utils.utils import query_chromadb, store_to_chromadb

load_dotenv()


# ==========================================================================
# Node 0: CONTEXT EXTRACTOR — LLM parses raw input into structured context
# ==========================================================================
def context_extractor(state) -> dict:
    """Use GroqLLM to extract structured pricing context from raw input paragraphs.

    Reads the raw fetched_content and category, then produces a structured
    extraction that the data_collector tools will use for targeted queries.
    """
    category = state.get("category", "Unknown")
    fetched_content = state.get("fetched_content", [])
    raw_text = "\n\n".join(fetched_content) if fetched_content else "(no content provided)"

    # Retrieve historical context from ChromaDB
    historical_context = query_chromadb("pricing_history", query=category, n_results=3)
    history_str = "\n".join(historical_context) if historical_context else "(No historical pricing data found)"

    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"You are a pricing intelligence analyst. Extract ALL relevant context from the "
        f"following raw content and from our database of historical research for the category: '{category}'.\n\n"
        f"---- HISTORICAL KNOWLEDGE ----\n{history_str}\n\n"
        f"---- CURRENT RAW CONTENT ----\n{raw_text[:10000]}\n\n"
        f"Extract and structure the following:\n\n"
        f"**1. Product / Service Identified:**\n"
        f"- Product name(s) mentioned\n"
        f"- Product category and sub-category\n"
        f"- Target customer segment (SMB, mid-market, enterprise, consumer)\n\n"
        f"**2. Competitors Mentioned:**\n"
        f"- List all competitor names\n"
        f"- Their approximate price points if mentioned\n\n"
        f"**3. Current Pricing Model:**\n"
        f"- Pricing model type (per-seat, usage-based, tiered, flat-rate, freemium)\n"
        f"- Price points and tiers mentioned\n"
        f"- Free tier / trial details\n\n"
        f"**4. Market Signals:**\n"
        f"- User pain points about pricing\n"
        f"- Willingness-to-pay indicators\n"
        f"- Market size or growth data\n\n"
        f"**5. Search Queries to Investigate:**\n"
        f"- Generate 3-5 specific Google search queries to find more pricing data\n"
        f"- Generate 2-3 Reddit search queries to find user pricing discussions\n"
        f"- Generate 2-3 competitor pricing page URLs to scrape (best guess)\n\n"
        f"Be thorough and specific. If information is not available, state 'Not mentioned'."
    )

    extracted = response.content

    return {
        "extracted_context": extracted,
        "messages": [
            HumanMessage(content=f"Context extracted from input for '{category}':\n\n{extracted[:500]}...")
        ],
    }


# ==========================================================================
# Individual tool functions (called in parallel by data_collector)
# ==========================================================================

def _search_serp(category: str) -> str:
    """Google search for pricing intelligence via SerpAPI."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return "(SERPAPI_API_KEY not set — skipped)"

    queries = [
        f"{category} pricing plans comparison",
        f"{category} pricing models willingness to pay",
    ]
    all_results = []

    for query in queries:
        try:
            resp = requests.get("https://serpapi.com/search.json", params={
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": 8,
            }, timeout=30)
            data = resp.json()

            # Check for API-level errors (invalid key, rate limit, etc.)
            if "error" in data:
                all_results.append(f"(SerpAPI error: {data['error']})")
                continue

            if resp.status_code != 200:
                all_results.append(f"(SerpAPI HTTP {resp.status_code} for '{query}')")
                continue

            for item in data.get("organic_results", [])[:5]:
                all_results.append(
                    f"**{item.get('title', '')}**\n"
                    f"{item.get('snippet', '')}\n"
                    f"URL: {item.get('link', '')}"
                )
        except Exception as e:
            all_results.append(f"(SerpAPI error for '{query}': {e})")

    return "\n\n".join(all_results) if all_results else "(No SerpAPI results)"


def _search_meta_ads(category: str) -> str:
    """Scrape Meta Ad Library public website for competitor pricing ads via Firecrawl."""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return "(FIRECRAWL_API_KEY not set — skipped)"

    try:
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)

        # Scrape the public Meta Ad Library search page
        encoded = category.replace(" ", "+")
        url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={encoded}&media_type=all"
        scraped = app.scrape(url, formats=["markdown"])
        content = scraped.get("markdown", "") if isinstance(scraped, dict) else str(scraped)
        return content[:4000] if content else f"(No Meta Ad Library data for '{category}')"
    except Exception as e:
        return f"(Meta Ad Library scrape error: {e})"


def _scrape_pricing_pages(category: str) -> str:
    """Use SerpAPI to find pricing page URLs, then scrape top ones with Firecrawl."""
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    serp_key = os.getenv("SERPAPI_API_KEY")

    if not firecrawl_key:
        return "(FIRECRAWL_API_KEY not set — skipped)"

    # Step 1: Find pricing page URLs via SerpAPI
    urls_to_scrape = []
    if serp_key:
        for search_q in [f"{category} pricing page", f"{category} pricing"]:
            if urls_to_scrape:
                break
            try:
                resp = requests.get("https://serpapi.com/search.json", params={
                    "q": search_q,
                    "api_key": serp_key,
                    "engine": "google",
                    "num": 5,
                }, timeout=30)
                data = resp.json()
                if "error" in data or resp.status_code != 200:
                    continue
                for item in data.get("organic_results", [])[:5]:
                    link = item.get("link", "")
                    if link:
                        urls_to_scrape.append(link)
            except Exception:
                pass

    if not urls_to_scrape:
        return f"(No pricing page URLs found for '{category}')"

    # Step 2: Scrape each URL with Firecrawl
    from firecrawl import FirecrawlApp
    app = FirecrawlApp(api_key=firecrawl_key)
    scraped = []

    for url in urls_to_scrape[:3]:
        try:
            result = app.scrape(url, formats=["markdown"])
            content = result.get("markdown", "") if isinstance(result, dict) else str(result)
            scraped.append(f"**[{url}]**\n{content[:3000]}")
        except Exception as e:
            scraped.append(f"**[{url}]** (Error: {e})")

    return "\n\n---\n\n".join(scraped) if scraped else "(No pages scraped)"


def _search_reddit(category: str) -> str:
    """Search Reddit for pricing discussions and willingness-to-pay signals."""
    queries = [
        f"{category} pricing too expensive",
        f"{category} best value worth the price",
    ]
    all_posts = []

    for query in queries:
        try:
            resp = requests.get("https://www.reddit.com/search.json", params={
                "q": query,
                "sort": "relevance",
                "limit": 8,
            }, headers={"User-Agent": "VeracityBot/1.0"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", [])[:5]:
                d = post.get("data", {})
                all_posts.append(
                    f"**r/{d.get('subreddit', '?')} — {d.get('title', '')}**\n"
                    f"Score: {d.get('score', 0)} | Comments: {d.get('num_comments', 0)}\n"
                    f"Text: {d.get('selftext', '')[:300]}"
                )
        except Exception as e:
            all_posts.append(f"(Reddit error for '{query}': {e})")

    return "\n\n".join(all_posts) if all_posts else f"(No Reddit results for '{category}')"


def _search_hn(category: str) -> str:
    """Search Hacker News via Algolia for pricing discussions."""
    queries = [
        f"{category} pricing",
        f"{category} willingness to pay",
    ]
    all_hits = []

    for query in queries:
        try:
            resp = requests.get("https://hn.algolia.com/api/v1/search", params={
                "query": query,
                "tags": "(story,comment)",
                "hitsPerPage": 8,
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", [])[:5]:
                title = hit.get("title") or hit.get("comment_text", "")[:200]
                points = hit.get("points", 0)
                author = hit.get("author", "unknown")
                obj_id = hit.get("objectID", "")
                all_hits.append(
                    f"**{title}**\n"
                    f"By: {author} | Points: {points or 'N/A'}\n"
                    f"URL: https://news.ycombinator.com/item?id={obj_id}"
                )
        except Exception as e:
            all_hits.append(f"(HN error for '{query}': {e})")

    return "\n\n".join(all_hits) if all_hits else f"(No HN results for '{category}')"


def _search_linkedin_ads(category: str) -> str:
    """Search LinkedIn Ad Library for B2B pricing signals via Firecrawl."""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return "(FIRECRAWL_API_KEY not set — skipped)"

    try:
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)
        encoded_category = category.replace(" ", "+")
        url = f"https://www.linkedin.com/ad-library/search?companyName={encoded_category}"
        scraped = app.scrape(url, formats=["markdown"])
        content = scraped.get("markdown", "") if isinstance(scraped, dict) else str(scraped)
        return content[:3000] if content else f"(No LinkedIn ad data for '{category}')"
    except Exception as e:
        return f"(LinkedIn Ad Library error: {e})"


def _analyze_content(category: str, content: str) -> str:
    """Use LLM to extract pricing patterns from fetched content."""
    if not content or content.strip() == "":
        return "(No content to analyze)"

    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Given the category '{category}', analyze this content for pricing intelligence.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Extract:\n"
        f"1. Pricing models used (freemium, tiered, usage-based, per-seat, etc.)\n"
        f"2. Price points and tier breakdowns\n"
        f"3. Pricing changes or increases\n"
        f"4. User sentiment on pricing\n"
        f"5. Willingness-to-pay signals\n"
        f"6. Competitive pricing positioning"
    )
    return response.content


# ==========================================================================
# Node 1: DATA COLLECTOR — runs all tools in parallel once
# ==========================================================================
def data_collector(state) -> dict:
    """Fire all pricing intelligence tools in parallel.

    Uses the extracted_context from context_extractor to build smarter
    queries for each tool. Runs all 7 tools concurrently.
    """
    category = state.get("category", "Unknown")
    fetched_content = state.get("fetched_content", [])
    extracted_context = state.get("extracted_context", "")
    content_str = "\n---\n".join(fetched_content[:5])

    # Use extracted context to build a richer search term
    search_category = category
    if extracted_context:
        # Append key competitor names and product names for better search results
        search_category = f"{category} ({extracted_context[:200]})"

    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(_search_serp, category): "serp_results",
            executor.submit(_search_meta_ads, category): "meta_ad_results",
            executor.submit(_scrape_pricing_pages, category): "scraped_pricing_pages",
            executor.submit(_search_reddit, category): "reddit_results",
            executor.submit(_search_hn, category): "hn_results",
            executor.submit(_search_linkedin_ads, category): "linkedin_ad_results",
            executor.submit(_analyze_content, category, content_str): "content_analysis",
        }

        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = f"(Error: {e})"

    # Build status summary
    tool_status = []
    for key, value in results.items():
        if value.startswith("(") and ("error" in value.lower() or "skipped" in value.lower() or "not set" in value.lower()):
            tool_status.append(f"  ⚠ {key}: {value[:80]}")
        else:
            tool_status.append(f"  ✓ {key}: {len(value)} chars collected")

    return {
        **results,
        "messages": [
            HumanMessage(content=(
                f"Data collection complete for '{category}'.\n" +
                "\n".join(tool_status)
            ))
        ],
    }


# ==========================================================================
# Node 2: COMPILER — LLM synthesizes all tool results
# ==========================================================================
def compiler(state) -> dict:
    """Compile all tool results into a unified pricing intelligence report.

    Reads all individual tool results from state and uses the LLM to
    synthesize a comprehensive pricing analysis.
    """
    category = state.get("category", "Unknown")

    # Gather all tool results
    tool_data = {
        "Google Search (SerpAPI)": state.get("serp_results", "(not available)"),
        "Meta Ad Library": state.get("meta_ad_results", "(not available)"),
        "Scraped Pricing Pages": state.get("scraped_pricing_pages", "(not available)"),
        "Reddit Discussions": state.get("reddit_results", "(not available)"),
        "Hacker News Discussions": state.get("hn_results", "(not available)"),
        "LinkedIn Ad Library": state.get("linkedin_ad_results", "(not available)"),
        "Content Analysis": state.get("content_analysis", "(not available)"),
    }

    # Build the compilation prompt
    tool_sections = []
    for source, data in tool_data.items():
        # Truncate each section to avoid token overflow
        truncated = data[:3000] if data else "(empty)"
        tool_sections.append(f"### {source}\n{truncated}")

    all_data = "\n\n".join(tool_sections)

    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"You are a Pricing Intelligence Analyst. Below are data collected from multiple "
        f"sources about pricing in the '{category}' market. Synthesize all of this into a "
        f"comprehensive pricing intelligence report.\n\n"
        f"## Collected Data\n\n{all_data}\n\n"
        f"## Required Analysis\n\n"
        f"Produce a structured report covering:\n\n"
        f"### 1. Pricing Model Validation\n"
        f"- What pricing models are used in this market?\n"
        f"- Which model performs best and why?\n\n"
        f"### 2. Competitive Pricing Benchmark\n"
        f"- Price points of major competitors\n"
        f"- Where does the market pricing cluster?\n\n"
        f"### 3. Willingness-to-Pay Analysis\n"
        f"- Evidence of WTP shifts from user discussions\n"
        f"- Price sensitivity indicators\n"
        f"- Maximum acceptable price points by segment\n\n"
        f"### 4. Ad Spend & Messaging Signals\n"
        f"- How are competitors positioning on price in their ads?\n"
        f"- Any aggressive pricing campaigns?\n\n"
        f"### 5. Strategic Recommendations\n"
        f"- Recommended pricing model\n"
        f"- Recommended price points with evidence\n"
        f"- Risks and opportunities\n\n"
        f"Be specific, cite data from the sources, and provide actionable recommendations."
    )

    final_report = response.content

    # Store final pricing report into ChromaDB to create long-term memory
    store_to_chromadb(
        collection_name="pricing_history",
        documents=[f"Category: {category}\n\n{final_report}"],
        metadatas=[{"category": category, "type": "pricing_report"}],
    )

    return {
        "analysis_result": final_report,
        "messages": [
            AIMessage(content=final_report),
        ],
    }
