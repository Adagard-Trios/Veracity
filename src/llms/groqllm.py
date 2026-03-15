from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv


class GroqLLM:
    """Wrapper class for Groq LLM access via LangChain."""

    def __init__(self):
        load_dotenv()
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables.")
        os.environ["GROQ_API_KEY"] = self.groq_api_key

    def get_llm(self, temperature: float = 0.0) -> ChatGroq:
        """Get a ChatGroq LLM instance.

        Args:
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).

        Returns:
            A configured ChatGroq instance.
        """
        try:
            llm = ChatGroq(
                api_key=self.groq_api_key,
                model="openai/gpt-oss-120b",
                temperature=temperature,
            )
            return llm
        except Exception as e:
            raise ValueError(f"Error creating Groq LLM instance: {e}")