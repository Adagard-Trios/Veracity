"""
Adjacent Node — Tool-calling agent for adjacent market analysis.

Uses LLM with domain-specific tools to identify adjacent market opportunities,
expansion vectors, and untapped segments based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
from src.states.adjacent_state import AdjacentState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_adjacent_markets(query: str, content: str) -> str:
    """Search through the fetched content to find information about adjacent markets.

    Args:
        query: What to search for in the content (e.g., 'adjacent markets in SaaS').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about adjacent markets.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract information relevant to adjacent markets "
        f"for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"Provide a structured analysis of adjacent market opportunities found."
    )
    return response.content


@tool
def identify_expansion_opportunities(category: str, content: str) -> str:
    """Identify expansion opportunities into adjacent markets based on the category.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for expansion opportunities.

    Returns:
        Structured analysis of expansion vectors and opportunities.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content and identify "
        f"expansion opportunities into adjacent markets.\n\nContent:\n{content[:8000]}\n\n"
        f"List potential adjacent markets, synergies, and recommended entry strategies."
    )
    return response.content


# All tools for this agent
adjacent_tools = [search_adjacent_markets, identify_expansion_opportunities]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: AdjacentState) -> dict:
    """Adjacent market analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(adjacent_tools)

    system_prompt = SystemMessage(content=(
        "You are an Adjacent Market Analysis Agent specializing in growth intelligence. "
        "Your task is to analyze the provided content and identify adjacent market opportunities "
        "for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Identify:\n"
        "1. Adjacent market segments with growth potential\n"
        "2. Cross-selling and up-selling opportunities\n"
        "3. Market adjacencies based on technology, customer base, or distribution channels\n"
        "4. Entry barriers and recommended strategies for each adjacent market\n\n"
        "Provide a comprehensive, actionable analysis."
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
