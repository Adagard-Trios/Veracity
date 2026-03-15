"""
Competitor Node — Tool-calling agent for competitor analysis.

Uses LLM with domain-specific tools to identify the competitive landscape,
SWOT analysis, and competitive positioning based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
from src.states.competitor_state import CompetitorState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_competitors(query: str, content: str) -> str:
    """Search through the fetched content to find information about competitors.

    Args:
        query: What to search for (e.g., 'main competitors in cloud storage').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about competitors.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract information about competitors "
        f"for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"List all competitors mentioned, their market position, and key differentiators."
    )
    return response.content


@tool
def analyze_competitor_strengths(category: str, content: str) -> str:
    """Perform a SWOT-style analysis of competitors in the given category.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for competitive intelligence.

    Returns:
        SWOT analysis and competitive positioning assessment.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content and perform "
        f"a competitive analysis.\n\nContent:\n{content[:8000]}\n\n"
        f"Provide:\n1. SWOT analysis of key competitors\n"
        f"2. Market share estimates\n3. Competitive advantages and weaknesses\n"
        f"4. Strategic recommendations for competitive positioning"
    )
    return response.content


# All tools for this agent
competitor_tools = [search_competitors, analyze_competitor_strengths]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: CompetitorState) -> dict:
    """Competitor analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(competitor_tools)

    system_prompt = SystemMessage(content=(
        "You are a Competitor Analysis Agent specializing in competitive intelligence. "
        "Your task is to analyze the provided content and build a comprehensive competitive "
        "landscape for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Identify:\n"
        "1. Direct and indirect competitors\n"
        "2. Market positioning of each competitor\n"
        "3. Strengths, weaknesses, opportunities, and threats (SWOT)\n"
        "4. Competitive gaps and strategic recommendations\n\n"
        "Provide a comprehensive, actionable competitive analysis."
    ))

    messages = state.get("messages", [])
    if not messages or not any(
        getattr(m, "type", None) == "system" for m in messages
    ):
        messages = [system_prompt] + list(messages)

    response = llm_with_tools.invoke(messages)

    return {
        "messages": [response],
        "analysis_result": response.content if not response.tool_calls else state.get("analysis_result", ""),
    }
