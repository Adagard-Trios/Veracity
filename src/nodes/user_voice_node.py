"""
User Voice Node — Context extraction + Parallel data collection + LLM compilation.

Architecture:
    context_extractor: LLM extracts current messaging, product claims, and target audience.
    data_collector: Fires tools (Reddit, HN, YouTube search, Review sites) to find real user voice.
    compiler: Synthesizes findings into a Positioning & Messaging Gap Report.

Focus: Does not tell what to build, but how to talk about what already exists.
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
# Node 0: CONTEXT EXTRACTOR — Parse raw input into messaging context
# ==========================================================================
def context_extractor(state) -> dict:
    """Extract current product messaging, positioning claims, and target audience."""
    category = state.get("category", "Unknown")
    fetched_content = state.get("fetched_content", [])
    raw_text = "\n\n".join(fetched_content) if fetched_content else "(no content provided)"

    # Retrieve historical messaging context from ChromaDB
    historical_context = query_chromadb("user_voice_history", query=category, n_results=3)
    history_str = "\n".join(historical_context) if historical_context else "(No historical messaging data found)"

    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"You are a Product Marketing & Positioning expert. The user has provided a paragraph "
        f"describing THEIR product in the category: '{category}'.\n\n"
        f"---- HISTORICAL KNOWLEDGE ----\n{history_str}\n\n"
        f"---- CURRENT RAW CONTENT ----\n{raw_text[:10000]}\n\n"
        f"Extract and structure:\n"
        f"1. Identity of the User's Product (What is it? Who is it for?)\n"
        f"2. User's Current Value Propositions (How are they currently talking about it?)\n"
        f"3. Key Competitors Mentioned (If any)\n"
        f"4. Desired Search Queries:\n"
        f"   - 2-3 Reddit queries to find user complaints about this specific niche/competitors\n"
        f"   - 2-3 Google queries to find Reddit/G2 reviews for this market\n"
        f"CRITICAL: Focus entirely on MESSAGING, POSITIONING, and HOW things are described."
    )

    extracted = response.content

    return {
        "extracted_context": extracted,
        "messages": [
            HumanMessage(content=f"Messaging context extracted for '{category}':\n\n{extracted[:500]}...")
        ],
    }


# ==========================================================================
# Individual Tool Functions
# ==========================================================================
def _search_reddit_feedback(category: str) -> str:
    """Search Reddit for how users actually talk about the category and their pain points."""
    queries = [
        f"{category} complaints issue",
        f"{category} alternatives why I switched",
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
                    f"Voice Snippet: {d.get('selftext', '')[:400]}"
                )
        except Exception as e:
            all_posts.append(f"(Reddit error for '{query}': {e})")

    return "\n\n".join(all_posts) if all_posts else f"(No Reddit feedback for '{category}')"


def _search_hn_feedback(category: str) -> str:
    """Search Hacker News for technical user positioning and feedback."""
    queries = [
        f"{category} vs",
        f"{category} feedback review",
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
                title = hit.get("title") or hit.get("comment_text", "")[:300]
                author = hit.get("author", "unknown")
                all_hits.append(f"**By {author}**: {title}")
        except Exception as e:
            all_hits.append(f"(HN error for '{query}': {e})")

    return "\n\n".join(all_hits) if all_hits else f"(No HN feedback for '{category}')"


def _search_youtube_reviews(category: str) -> str:
    """Search SerpAPI for YouTube review titles and snippets to see how creators position them."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return "(SERPAPI_API_KEY not set — skipped)"

    try:
        resp = requests.get("https://serpapi.com/search.json", params={
            "q": f"site:youtube.com {category} review honest opinion",
            "api_key": api_key,
            "engine": "google",
            "num": 8,
        }, timeout=30)
        data = resp.json()

        if "error" in data:
            return f"(SerpAPI error: {data['error']})"

        results = []
        for item in data.get("organic_results", [])[:5]:
            results.append(
                f"**{item.get('title', '')}**\nSnippet: {item.get('snippet', '')}"
            )
        return "\n\n".join(results) if results else "(No YouTube reviews found)"
    except Exception as e:
        return f"(SerpAPI YouTube error: {e})"


def _search_review_sites(category: str) -> str:
    """Search SerpAPI for G2/Capterra/TrustRadius review snippets to extract user voice."""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return "(SERPAPI_API_KEY not set — skipped)"

    try:
        resp = requests.get("https://serpapi.com/search.json", params={
            "q": f"(site:g2.com OR site:capterra.com) {category} review pros cons",
            "api_key": api_key,
            "engine": "google",
            "num": 8,
        }, timeout=30)
        data = resp.json()

        if "error" in data:
            return f"(SerpAPI error: {data['error']})"

        results = []
        for item in data.get("organic_results", [])[:6]:
            results.append(
                f"**{item.get('title', '')}**\nSnippet: {item.get('snippet', '')}"
            )
        return "\n\n".join(results) if results else "(No review site snippets found)"
    except Exception as e:
        return f"(SerpAPI Review Sites error: {e})"


def _scrape_community_reviews(category: str) -> str:
    """Find and scrape independent long-form reviews from community blogs (Medium, Substack, etc)."""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    serp_key = os.getenv("SERPAPI_API_KEY")
    
    if not api_key or not serp_key:
        return "(FIRECRAWL_API_KEY or SERPAPI_API_KEY not set — skipped)"

    urls_to_scrape = []
    
    try:
        # Step 1: Find independent reviews (excluding corporate sites)
        resp = requests.get("https://serpapi.com/search.json", params={
            "q": f"{category} review (site:medium.com OR site:substack.com OR site:dev.to) -site:g2.com",
            "api_key": serp_key,
            "engine": "google",
            "num": 5,
        }, timeout=30)
        data = resp.json()

        for item in data.get("organic_results", [])[:3]:
            link = item.get("link", "")
            if link:
                urls_to_scrape.append(link)
    except Exception as e:
        pass

    if not urls_to_scrape:
        return f"(No independent long-form reviews found to scrape for '{category}')"

    # Step 2: Scrape them
    from firecrawl import FirecrawlApp
    app = FirecrawlApp(api_key=api_key)
    scraped = []

    for url in urls_to_scrape:
        try:
            result = app.scrape(url, formats=["markdown"])
            content = result.get("markdown", "") if isinstance(result, dict) else str(result)
            # Truncate to avoid token explosion, but capture enough for voice profiling
            scraped.append(f"**[{url}]**\n{content[:2500]}")
        except Exception as e:
            scraped.append(f"**[{url}]** (Error: {e})")

    return "\n\n---\n\n".join(scraped) if scraped else "(No pages scraped)"


def _analyze_competitor_messaging(category: str, content: str) -> str:
    """Use LLM to extract how competitors talk about themselves in the fetched content."""
    if not content or content.strip() == "":
        return "(No content to analyze)"

    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze this content to determine HOW competitors position themselves in the '{category}' market.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Extract:\n"
        f"1. Words and phrases they over-use\n"
        f"2. Core promises and value propositions\n"
        f"3. Tone of voice (e.g., deeply technical, playful, enterprise-stiff)\n"
        f"4. What they ARE NOT saying (the obvious gaps)"
    )
    return response.content


# ==========================================================================
# Node 1: DATA COLLECTOR — Fire tools in parallel
# ==========================================================================
def data_collector(state) -> dict:
    """Run real user voice and messaging research tools in parallel."""
    category = state.get("category", "Unknown")
    fetched_content = state.get("fetched_content", [])
    extracted_context = state.get("extracted_context", "")
    content_str = "\n---\n".join(fetched_content[:5])

    search_category = category
    if extracted_context:
        search_category = f"{category} ({extracted_context[:100]})"

    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_search_reddit_feedback, search_category): "reddit_feedback",
            executor.submit(_search_hn_feedback, search_category): "hn_feedback",
            executor.submit(_search_youtube_reviews, category): "youtube_reviews",
            executor.submit(_search_review_sites, category): "review_site_snippets",
            executor.submit(_scrape_community_reviews, category): "scraped_reviews",
            executor.submit(_analyze_competitor_messaging, category, content_str): "competitor_messaging",
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
            tool_status.append(f"  ⚠ {key}: {value[:80]}")
        else:
            tool_status.append(f"  ✓ {key}: {len(value)} chars collected")

    return {
        **results,
        "messages": [
            HumanMessage(content=(
                f"Data collection complete for '{category}' messaging gaps.\n" +
                "\n".join(tool_status)
            ))
        ],
    }


# ==========================================================================
# Node 2: COMPILER — Synthesize into Messaging & Positioning Gap Report
# ==========================================================================
def compiler(state) -> dict:
    """Compile tool results into a final Positioning & Messaging Gap Report."""
    category = state.get("category", "Unknown")
    extracted_context = state.get("extracted_context", "")

    tool_data = {
        "Reddit User Voice": state.get("reddit_feedback", ""),
        "HN Community Voice": state.get("hn_feedback", ""),
        "YouTube Creator Voice": state.get("youtube_reviews", ""),
        "G2/Capterra Sentiments": state.get("review_site_snippets", ""),
        "Independent Scraped Reviews": state.get("scraped_reviews", ""),
        "Competitor Messaging Analysis": state.get("competitor_messaging", ""),
    }

    sections = []
    for source, data in tool_data.items():
        truncated = data[:3000] if data else "(empty)"
        sections.append(f"### {source}\n{truncated}")

    all_data = "\n\n".join(sections)

    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"You are a strict Product Positioning and Messaging Expert. The user has provided "
        f"information about their EXISTING product in the '{category}' market.\n\n"
        f"CRITICAL RULE: DO NOT tell the user what features to build. DO NOT provide a product roadmap. "
        f"Your ONLY job is to tell the user HOW TO TALK ABOUT what they already have. You must find the "
        f"positioning and messaging gaps based on how real users speak.\n\n"
        f"## Background Context (The User's Product)\n{extracted_context[:2000]}\n\n"
        f"## Gathered Market Data (How the market/users talk)\n{all_data}\n\n"
        f"Produce a highly strategic 'Positioning and Messaging Gap Report' answering:\n\n"
        f"### 1. The 'Sea of Sameness' (What to avoid saying)\n"
        f"- What is every competitor saying? (The jargon, the clichés)\n"
        f"- What positioning is completely exhausted in this category?\n\n"
        f"### 2. The Real User Voice (The vocabulary to steal)\n"
        f"- What exact words/phrases do users use on Reddit/HN/Reviews when they are frustrated?\n"
        f"- What do they actually value vs. what corporate marketing *thinks* they value?\n\n"
        f"### 3. The Messaging Gap (The Opportunity for the User's Product)\n"
        f"- Based on the user's product description, where is the whitespace in their narrative?\n"
        f"- What user pain points align perfectly with the user's existing product that they aren't emphasizing enough?\n\n"
        f"### 4. Recommended Positioning Hooks\n"
        f"- 3-4 specific messaging angles/copywriting hooks that talk about their EXISTING product in a refreshing way.\n"
        f"- Examples of 'Stop saying X, start saying Y'."
    )

    final_report = response.content

    # Store final user voice report into ChromaDB to create long-term memory
    store_to_chromadb(
        collection_name="user_voice_history",
        documents=[f"Category: {category}\n\n{final_report}"],
        metadatas=[{"category": category, "type": "messaging_gap_report"}],
    )

    return {
        "analysis_result": final_report,
        "messages": [
            AIMessage(content=final_report),
        ],
    }
