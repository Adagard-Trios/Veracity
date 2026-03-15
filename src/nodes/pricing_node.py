"""
Pricing Node — Tool-calling agent for pricing analysis.

Uses LLM with domain-specific tools to analyze pricing strategies,
models, elasticity, and competitive pricing based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
from src.states.pricing_state import PricingState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_pricing_data(query: str, content: str) -> str:
    """Search through the fetched content to find pricing-related information.

    Args:
        query: What pricing data to search for (e.g., 'pricing tiers for CRM tools').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about pricing.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract pricing-related information "
        f"for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"Identify pricing models, price points, tiers, and pricing strategies."
    )
    return response.content


@tool
def analyze_pricing_strategies(category: str, content: str) -> str:
    """Analyze pricing strategies used in the market for the given category.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for pricing intelligence.

    Returns:
        Detailed pricing strategy analysis and recommendations.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content for pricing strategies.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Provide:\n1. Common pricing models in this market\n"
        f"2. Price point analysis and competitive benchmarking\n"
        f"3. Pricing elasticity insights\n"
        f"4. Freemium vs premium analysis\n"
        f"5. Recommended pricing strategy and positioning"
    )
    return response.content


# All tools for this agent
pricing_tools = [search_pricing_data, analyze_pricing_strategies]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: PricingState) -> dict:
    """Pricing analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(pricing_tools)

    system_prompt = SystemMessage(content=(
        "You are a Pricing Analysis Agent specializing in growth intelligence. "
        "Your task is to analyze the provided content and deliver actionable pricing "
        "insights for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Deliver:\n"
        "1. Current pricing landscape in this market\n"
        "2. Competitive pricing benchmarks\n"
        "3. Value-based vs cost-based pricing analysis\n"
        "4. Price sensitivity and elasticity insights\n"
        "5. Recommended pricing strategy with justification\n\n"
        "Provide a comprehensive, actionable pricing analysis."
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
