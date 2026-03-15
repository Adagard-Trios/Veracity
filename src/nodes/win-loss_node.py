"""
Win-Loss Node — Tool-calling agent for win-loss analysis.

Uses LLM with domain-specific tools to analyze deal win/loss patterns,
conversion factors, and sales intelligence based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
import importlib
_win_loss_state_mod = importlib.import_module("src.states.win-loss_state")
WinLossState = _win_loss_state_mod.WinLossState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_win_loss_data(query: str, content: str) -> str:
    """Search through the fetched content to find win/loss deal data.

    Args:
        query: What win/loss data to search for (e.g., 'reasons for deal losses').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about win/loss patterns.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract win/loss intelligence "
        f"for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"Identify win rates, loss reasons, deal patterns, and conversion factors."
    )
    return response.content


@tool
def analyze_deal_patterns(category: str, content: str) -> str:
    """Analyze deal patterns to identify win/loss factors in the given category.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for deal patterns.

    Returns:
        Detailed win/loss pattern analysis with recommendations.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content for win/loss patterns.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Provide:\n1. Win rate analysis and trends\n"
        f"2. Top reasons for winning deals\n"
        f"3. Top reasons for losing deals\n"
        f"4. Competitive win/loss breakdown\n"
        f"5. Deal cycle analysis\n"
        f"6. Recommendations to improve win rates"
    )
    return response.content


# All tools for this agent
win_loss_tools = [search_win_loss_data, analyze_deal_patterns]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: WinLossState) -> dict:
    """Win-loss analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(win_loss_tools)

    system_prompt = SystemMessage(content=(
        "You are a Win-Loss Analysis Agent specializing in sales intelligence. "
        "Your task is to analyze the provided content and identify deal win/loss patterns, "
        "conversion factors, and competitive dynamics for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Deliver:\n"
        "1. Win/loss ratio analysis\n"
        "2. Key factors driving wins\n"
        "3. Key factors driving losses\n"
        "4. Competitive displacement patterns\n"
        "5. Sales process improvement recommendations\n\n"
        "Provide a comprehensive, actionable win-loss analysis."
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
