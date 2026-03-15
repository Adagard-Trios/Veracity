"""
User Voice Node — Tool-calling agent for user voice / customer feedback analysis.

Uses LLM with domain-specific tools to analyze customer feedback, sentiment,
NPS, and user experience signals based on fetched content.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from src.llms.groqllm import GroqLLM
from src.states.user_voice_state import UserVoiceState


# ---------------------------------------------------------------------------
# Domain-specific tools
# ---------------------------------------------------------------------------
@tool
def search_user_feedback(query: str, content: str) -> str:
    """Search through the fetched content to find user feedback and reviews.

    Args:
        query: What feedback to search for (e.g., 'user complaints about onboarding').
        content: The fetched content to analyze.

    Returns:
        Relevant excerpts and analysis about user feedback.
    """
    llm = GroqLLM().get_llm(temperature=0.1)
    response = llm.invoke(
        f"Analyze the following content and extract user feedback, reviews, and voice "
        f"of customer data for the query: '{query}'.\n\nContent:\n{content[:8000]}\n\n"
        f"Identify user pain points, praise, feature requests, and sentiment indicators."
    )
    return response.content


@tool
def analyze_sentiment(category: str, content: str) -> str:
    """Perform sentiment analysis on user feedback for the given category.

    Args:
        category: The business/product category being analyzed.
        content: The fetched content to analyze for sentiment.

    Returns:
        Sentiment analysis with categorized feedback themes.
    """
    llm = GroqLLM().get_llm(temperature=0.2)
    response = llm.invoke(
        f"Given the category '{category}', analyze the following content for user sentiment.\n\n"
        f"Content:\n{content[:8000]}\n\n"
        f"Provide:\n1. Overall sentiment score and breakdown\n"
        f"2. Top positive themes and praise points\n"
        f"3. Top negative themes and pain points\n"
        f"4. Feature requests and unmet needs\n"
        f"5. NPS and satisfaction indicators\n"
        f"6. Recommendations for product improvement"
    )
    return response.content


# All tools for this agent
user_voice_tools = [search_user_feedback, analyze_sentiment]


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------
def agent_node(state: UserVoiceState) -> dict:
    """User voice analysis agent node."""
    llm = GroqLLM().get_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools(user_voice_tools)

    system_prompt = SystemMessage(content=(
        "You are a User Voice Analysis Agent specializing in customer intelligence. "
        "Your task is to analyze the provided content and extract customer feedback, "
        "sentiment, and user experience insights for the given category.\n\n"
        f"Category: {state.get('category', 'Unknown')}\n\n"
        "You have access to the following fetched content from various sources:\n"
        + "\n---\n".join(state.get("fetched_content", [])[:5])
        + "\n\nUse your tools to thoroughly analyze this content. Deliver:\n"
        "1. Voice of Customer (VoC) summary\n"
        "2. Sentiment distribution (positive/neutral/negative)\n"
        "3. Key themes in user feedback\n"
        "4. Unmet customer needs and feature gaps\n"
        "5. User experience improvement recommendations\n\n"
        "Provide a comprehensive, empathetic customer voice analysis."
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
