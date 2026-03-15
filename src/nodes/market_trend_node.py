"""
Market Trend Node — Tool-calling agent for market trend analysis.

Uses LLM with domain-specific tools to identify market trends, growth patterns,
and emerging signals based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
from src.states.market_trend_state import MarketTrendState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_market_trends(query: str, content: str) -> str:
    """Search through the fetched content to find market trend information.

    Args:
        query: What trends to search for (e.g., 'AI adoption trends in healthcare').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about market trends.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract market trend information "
        f"for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"Identify current trends, growth rates, emerging patterns, and market drivers."
    )
    return response.content


@tool
def analyze_trend_data(category: str, content: str) -> str:
    """Analyze trend data to identify growth patterns and emerging signals.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for trends.

    Returns:
        Detailed trend analysis with growth projections and signals.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content for market trends.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Provide:\n1. Key market trends (macro and micro)\n"
        f"2. Growth rate estimates and projections\n"
        f"3. Emerging signals and early indicators\n"
        f"4. Technology trends impacting the market\n"
        f"5. Regulatory and policy trends"
    )
    return response.content


# All tools for this agent
market_trend_tools = [search_market_trends, analyze_trend_data]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: MarketTrendState) -> dict:
    """Market trend analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(market_trend_tools)

    system_prompt = SystemMessage(content=(
        "You are a Market Trend Analysis Agent specializing in growth intelligence. "
        "Your task is to analyze the provided content and identify key market trends, "
        "growth patterns, and emerging signals for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Identify:\n"
        "1. Macro and micro market trends\n"
        "2. Market growth trajectory and key drivers\n"
        "3. Technology disruption signals\n"
        "4. Consumer behavior shifts\n"
        "5. Forecasts and projections\n\n"
        "Provide a comprehensive, data-driven trend analysis."
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
