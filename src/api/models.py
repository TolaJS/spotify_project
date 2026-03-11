from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

class ChatMessagePayload(BaseModel):
    query: str
    session_id: Optional[str] = None

class WsMessage(BaseModel):
    """Format for messages sent over the WebSocket."""
    type: str = Field(..., description="Message type: 'status', 'token', 'result', 'error'")
    content: Any
    metadata: Optional[Dict[str, Any]] = None
