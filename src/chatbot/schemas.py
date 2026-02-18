from typing import TypedDict, Optional, List, Any


class Turn(TypedDict):
    """A single conversation turn."""
    query: str                      # what the user actually said
    rewritten_query: Optional[str]  # None on first turn, rewritten string on follow-ups
    response: str                   # the assistant's response text
    success: bool                   # from Orchestrator result
    timestamp: float                # time.time()
    step_results: Optional[List[Any]]  # orchestrator step results, forwarded as context to next turn


class Session(TypedDict):
    """An in-memory conversation session."""
    session_id: str
    turns: List[Turn]
    created_at: float
    last_active: float


class ChatResponse(TypedDict):
    """Return type for ConversationManager.chat()."""
    session_id: str
    response: str
    success: bool
    rewritten_query: Optional[str]  # None if first turn (no rewrite happened)
    turn_number: int                # 0-indexed
