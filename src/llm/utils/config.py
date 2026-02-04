import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# OpenAI config (for Router)
OPENAI_MODEL = "gpt-5-mini"
OPENAI_TEMPERATURE = 0

# Gemini config (for Graph RAG)
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_TEMPERATURE = 0

# Neo4j config
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


def get_llm(model: str = None, temperature: float = None) -> ChatOpenAI:
    """Get configured OpenAI LLM instance.

    Args:
        model: Override default model
        temperature: Override default temperature

    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        model=model or OPENAI_MODEL,
        temperature=temperature if temperature is not None else OPENAI_TEMPERATURE,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def get_gemini_llm(model: str = None, temperature: float = None) -> ChatGoogleGenerativeAI:
    """Get configured Google Gemini LLM instance.

    Args:
        model: Override default model
        temperature: Override default temperature

    Returns:
        Configured ChatGoogleGenerativeAI instance
    """
    return ChatGoogleGenerativeAI(
        model=model or GEMINI_MODEL,
        temperature=temperature if temperature is not None else GEMINI_TEMPERATURE,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )


def get_neo4j_config() -> dict:
    """Get Neo4j connection configuration.

    Returns:
        Dict with uri, user, password
    """
    return {
        "uri": NEO4J_URI,
        "user": NEO4J_USER,
        "password": NEO4J_PASSWORD,
    }
