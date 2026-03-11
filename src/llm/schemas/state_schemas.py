"""State schemas for the LangGraph hierarchical agents."""

from typing import Annotated, TypedDict, List, Dict, Any, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator

def merge_dict(a: dict, b: dict) -> dict:
    """Merges two dictionaries, commonly used to aggregate tool results into a final context block."""
    result = a.copy()
    result.update(b)
    return result

class GlobalState(TypedDict):
    """The main state object passed through the Manager Graph.
    
    Attributes:
        messages: The conversation history, including Human, AI, and Tool messages.
                  Uses `add_messages` to automatically append new messages rather than overwrite.
        step_results: A collected dictionary of raw, structured data returned by the worker agents.
                      This replicates the old system's context gathering, allowing the wrapper
                      to extract it and save it to Neo4j.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    step_results: Annotated[Dict[str, Any], merge_dict]


class WorkerState(TypedDict):
    """The state object passed to individual Worker Sub-Graphs (Spotify or Graph RAG).
    
    Attributes:
        messages: The isolated thought process and tool calls for this specific task.
                  We intentionally do not pass the entire GlobalState history down 
                  to prevent confusing the worker with unrelated context.
    """
    messages: Annotated[list[BaseMessage], add_messages]
