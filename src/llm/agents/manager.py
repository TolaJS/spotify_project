"""The Manager Agent for LangGraph.

This acts as the Supervisor, delegating to the Spotify and GraphRAG sub-graphs.
"""

from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

# Import the state schemas and prompts
from ..schemas.state_schemas import GlobalState
from ..prompts.manager_prompts import MANAGER_SYSTEM_PROMPT
from ..utils.config import get_gemini_llm

# Import our worker builders
from .spotify import build_spotify_worker
from .graph_rag import build_graph_worker

# 1. Build the sub-agents
spotify_worker = build_spotify_worker()
graph_worker = build_graph_worker()

def _extract_text(content) -> str:
    """Helper to extract raw text from Gemini's list format if needed."""
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)
        return "".join(text_parts)
    return str(content)

# 2. Define the Tools that the Manager uses to talk to the workers

@tool
def ask_spotify_worker(query: str) -> str:
    """Delegates a live Spotify task (playing, queuing, creating playlists, searching the global catalog) to the Spotify Worker.
    
    Args:
        query: The specific instruction for the Spotify worker (e.g., 'Queue Gods Plan by Drake', 'Create a playlist called Gym').
    """
    # Invoke the compiled sub-graph
    result = spotify_worker.invoke({"messages": [HumanMessage(content=query)]})
    # The last message is the worker's final response
    return _extract_text(result["messages"][-1].content)

@tool
def ask_graph_worker(query: str) -> str:
    """Delegates a historical listening history task to the Graph RAG Worker.
    Use this to find the user's top tracks, top artists, or query their personal music database.
    
    Args:
        query: The specific question about the user's history (e.g., 'What is my most played song this month?').
    """
    # Invoke the compiled sub-graph
    result = graph_worker.invoke({"messages": [HumanMessage(content=query)]})
    return _extract_text(result["messages"][-1].content)

@tool
def google_search(query: str) -> str:
    """Searches the web for general music trivia, news, or facts not found in Spotify or user history.
    
    Args:
        query: The search query (e.g., 'Who won album of the year 2024').
    """
    # Use a secondary Gemini instance with native Search Grounding enabled
    search_llm = get_gemini_llm(model="gemini-3-flash-preview", temperature=0.0, enable_search=True)
    try:
        response = search_llm.invoke(f"Search the web and answer this concisely: {query}")
        
        # Handle list vs string content (Google GenAI sometimes returns list of dicts)
        raw_content = response.content
        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            return "".join(text_parts)
            
        return str(raw_content)
    except Exception as e:
        return f"Web search failed: {e}"

# 3. Compile the Manager Agent
manager_tools = [ask_spotify_worker, ask_graph_worker, google_search]

def build_manager_agent():
    """Builds and returns the top-level Manager ReAct agent."""
    # We use the most capable model for the manager to ensure excellent synthesis and routing.
    # We turn OFF native search here to prevent LangGraph tool confusion, 
    # and instead provide the explicitly wrapped google_search tool above.
    llm = get_gemini_llm(model="gemini-3-flash-preview", temperature=0.3, enable_search=False)
    
    manager_agent = create_agent(
        llm,
        tools=manager_tools,
        system_prompt=MANAGER_SYSTEM_PROMPT
    )
    
    return manager_agent