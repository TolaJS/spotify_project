import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect, Cookie
from typing import Dict, Optional

from llm.langgraph_orchestrator import LangGraphOrchestrator

logger = logging.getLogger(__name__)

# Global Conversation Manager instance for the server
manager = LangGraphOrchestrator()

# Currently active WebSocket connections mapped by session_id
active_connections: Dict[str, WebSocket] = {}

async def chat_endpoint(websocket: WebSocket, spotify_user_id: Optional[str] = Cookie(default=None, alias="__session")):
    await websocket.accept()
    session_id = None
    logger.info(f"New WebSocket connection. Cookie spotify_user_id: {spotify_user_id}")
    try:
        data = await websocket.receive_text()
        payload = json.loads(data)

        session_id = payload.get("session_id", "guest")
        active_connections[session_id] = websocket

        # Cookie is stripped by Firebase when the WebSocket connects cross-origin.
        # Fall back to the user_id sent in the handshake payload.
        if not spotify_user_id:
            spotify_user_id = payload.get("user_id")

        # Load the session into memory if it exists in Firestore.
        # The frontend renders history via the REST endpoint, so no status message needed here.
        manager.get_session(session_id)
        
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "ping":
                continue

            query = payload.get("query")
            message_id = payload.get("message_id")
            timezone = payload.get("timezone")

            if not query:
                continue

            await websocket.send_json({"type": "status", "content": "Thinking..."})

            # Define a coroutine to handle the actual chat processing and sending the response.
            async def process_chat(q, m_id, s_id, u_id, tz):
                try:
                    response = await asyncio.to_thread(manager.chat, q, s_id, u_id, tz)
                    
                    await websocket.send_json({
                        "type": "result",
                        "content": response["response"],
                        "metadata": {
                            "success": response["success"],
                            "session_id": response["session_id"],
                            "turn_number": response["turn_number"],
                            "message_id": m_id
                        }
                    })
                except Exception as e:
                    logger.error(f"Chat error: {e}")
                    await websocket.send_json({"type": "error", "content": str(e), "metadata": {"message_id": m_id}})
                    # Ensure we log if we can't save on error
                    if not u_id:
                        logger.warning(f"Cannot save session {s_id} on error: missing user_id")
                    manager.close_session(s_id, u_id)

            # Fire and forget the processing task
            asyncio.create_task(process_chat(query, message_id, session_id, spotify_user_id, timezone))

    except WebSocketDisconnect:
        logger.info(f"Client {session_id} disconnected. User ID: {spotify_user_id}")
        if session_id in active_connections:
            del active_connections[session_id]
        
        # When the user disconnects (closes tab or navigates away), save the session to Firestore
        if session_id and spotify_user_id:
            logger.info(f"Triggering close_session from WS disconnect for {session_id}")
            manager.close_session(session_id, user_id=spotify_user_id)
        elif not spotify_user_id:
            logger.warning(f"WebSocket disconnected but NO spotify_user_id cookie was found. Session {session_id} not saved!")

