"""
User Voice State — State for the User Voice Analysis sub-graph.

Architecture: context_extractor → data_collector (parallel tools) → compiler (LLM synthesis)

Focuses on positioning and messaging gaps (how to talk about what exists).
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class UserVoiceState(TypedDict):
    """State for the user voice / messaging gap analysis graph.

    Attributes:
        messages: Chat message history.
        category: The business/product category being analyzed.
        fetched_content: Raw content from all sources for analysis.
        extracted_context: Structured context extracted by LLM (current messaging, target audience).
        reddit_feedback: Results from Reddit user feedback discussions.
        hn_feedback: Results from HN tech community feedback.
        youtube_reviews: Results from SerpAPI for YouTube review titles/snippets.
        review_site_snippets: Results from SerpAPI for G2/Capterra review snippets.
        competitor_messaging: Results from LLM analysis of competitor messaging in fetched content.
        analysis_result: Final compiled positioning and messaging gap report.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]

    # Extracted structured context (populated by context_extractor)
    extracted_context: str

    # Individual tool results (populated in parallel by data_collector)
    reddit_feedback: str
    hn_feedback: str
    review_site_snippets: str
    scraped_reviews: str
    competitor_messaging: str

    # Final output (populated by compiler)
    analysis_result: str
