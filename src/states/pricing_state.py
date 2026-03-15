"""
Pricing State — State for the Pricing Intelligence sub-graph.

Architecture: context_extractor → data_collector (parallel tools) → compiler (LLM synthesis)

Stores input context, extracted context, individual tool results, and the final compiled analysis.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class PricingState(TypedDict):
    """State for the pricing intelligence graph.

    Attributes:
        messages: Chat message history.
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        extracted_context: Structured context extracted by LLM from raw content.
        serp_results: Results from SerpAPI Google search.
        meta_ad_results: Results from Meta Ad Library.
        scraped_pricing_pages: Results from Firecrawl pricing page scraping.
        reddit_results: Results from Reddit pricing discussions.
        hn_results: Results from HN Algolia pricing discussions.
        linkedin_ad_results: Results from LinkedIn Ad Library.
        content_analysis: Results from LLM analysis of fetched content.
        analysis_result: Final compiled pricing intelligence output.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]

    # Extracted structured context (populated by context_extractor)
    extracted_context: str

    # Individual tool results (populated in parallel by data_collector)
    serp_results: str
    meta_ad_results: str
    scraped_pricing_pages: str
    reddit_results: str
    hn_results: str
    linkedin_ad_results: str
    content_analysis: str

    # Final output (populated by compiler)
    analysis_result: str
