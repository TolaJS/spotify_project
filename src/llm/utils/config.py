import os
from langchain_google_genai import ChatGoogleGenerativeAI

# Gemini config
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_TEMPERATURE = 0

# BigQuery config
BQ_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2")
BQ_DATASET_ID = os.getenv("BQ_DATASET_ID", "timber")


def get_gemini_llm(model: str = None, temperature: float = None, enable_search: bool = False) -> ChatGoogleGenerativeAI:
    """Get configured Google Gemini LLM instance.

    Args:
        model: Override default model
        temperature: Override default temperature
        enable_search: If True, natively binds Google Search grounding tool to the model.

    Returns:
        Configured ChatGoogleGenerativeAI instance
    """
    kwargs = {
        "model": model or GEMINI_MODEL,
        "temperature": temperature if temperature is not None else GEMINI_TEMPERATURE,
        "google_api_key": os.getenv("GOOGLE_API_KEY"),
    }
    
    # LangChain v0.2+ integration for Gemini native tools
    llm = ChatGoogleGenerativeAI(**kwargs)
    
    if enable_search:
        # Binds the native Google Search grounding tool to the LLM
        return llm.bind_tools([{"google_search": {}}])
        
    return llm


def get_bigquery_config() -> dict:
    """Get BigQuery connection configuration."""
    return {
        "project_id": BQ_PROJECT_ID,
        "dataset_id": BQ_DATASET_ID,
    }
