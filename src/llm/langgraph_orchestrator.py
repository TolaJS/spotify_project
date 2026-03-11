"""LangGraph Orchestrator - A stateful bridge between FastAPI, Neo4j, and the LangGraph Manager."""

import json
import logging
import time
import uuid
from typing import Optional, Dict

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

# Import the main LangGraph agent
from .agents.manager import build_manager_agent

# Reuse the schemas and history DB from the old setup 
# so we don't have to rewrite the WebSocket integration yet.
from chatbot.schemas import Turn, Session, ChatResponse
from chatbot.history_db import HistoryRepository
from auth.oauth_handler import current_user_id as spotify_user_ctx

logger = logging.getLogger(__name__)

class LangGraphOrchestrator:
    """Manages multi-turn conversations using LangGraph and Neo4j memory."""

    DEFAULT_TIMEOUT_SECONDS = 15 * 60  # 15 minutes

    def __init__(
        self,
        session_timeout: float = None,
    ):
        self._session_timeout = session_timeout or self.DEFAULT_TIMEOUT_SECONDS
        self._sessions: Dict[str, Session] = {}
        
        # Build the LangGraph Manager Brain
        self.manager_app = build_manager_agent()
        
        # Initialize Database connection
        self._history_repo = self._init_repo()

    def _init_repo(self):
        import sys
        import os
        try:
            # Add graph-rag to path since it has a dash in the folder name
            sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../graph-rag')))
            from neo4j_db import Neo4jDatabase
            from llm.utils.config import get_neo4j_config
            
            config = get_neo4j_config()
            db = Neo4jDatabase(uri=config["uri"], auth=(config["user"], config["password"]))
            db.connect()
            return HistoryRepository(db)
        except Exception as e:
            logger.error(f"Failed to initialize HistoryRepository: {e}")
            return None

    def _build_langgraph_messages(self, turns: list[Turn]) -> list:
        """Converts chronological Session turns into LangChain BaseMessage objects."""
        messages = []
        for turn in turns:
            # 1. Add what the user said
            messages.append(HumanMessage(content=turn["query"]))
            
            # 2. Add the tool results if any (Context injection)
            if turn.get("step_results"):
                # We inject the hidden structured data back into the AI's context
                context_str = json.dumps(turn["step_results"])
                # We format it as a generic tool message so the LLM accepts it as past context
                messages.append(ToolMessage(
                    content=context_str, 
                    name="previous_context", 
                    tool_call_id=f"ctx_{uuid.uuid4().hex[:8]}"
                ))
                
            # 3. Add what the AI said
            messages.append(AIMessage(content=turn["response"]))
            
        return messages

    def chat(self, query: str, session_id: Optional[str] = None, user_id: Optional[str] = None) -> ChatResponse:
        """Process a user message using LangGraph."""
        self._cleanup_expired()

        # Resolve or create the session wrapper
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
        else:
            session = self._create_session(session_id)

        # Build the exact message history array for LangGraph
        lg_messages = self._build_langgraph_messages(session["turns"])
        
        # Inject the absolute current time and the User ID into the prompt
        import datetime
        current_time = datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
        uid_context = user_id if user_id else "kanljakm68dmhxs19itsmgbku"
        
        system_context = f"System Context:\n- The current date and time is exactly {current_time}.\n- The current active Spotify User ID is: {uid_context}."
        lg_messages.append(SystemMessage(content=system_context))
        
        # Append the new user query
        lg_messages.append(HumanMessage(content=query))
        
        # Invoke the LangGraph Manager Agent
        # We pass the entire history array natively; no QueryRewriter needed!
        # Set the user context so all Spotify tools in this call chain know
        # which user's token to use. ContextVar is thread-safe —
        # each asyncio.to_thread call gets its own copy of the context.
        ctx_token = spotify_user_ctx.set(user_id) if user_id else None
        try:
            result_state = self.manager_app.invoke({"messages": lg_messages})
            
            # The final message in the state is the AI's synthesized response
            final_message = result_state["messages"][-1]
            
            # Handle list vs string content (Google GenAI sometimes returns list of dicts)
            raw_content = final_message.content
            if isinstance(raw_content, list):
                # Extract text from the list of content blocks
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict) and "text" in block:
                        text_parts.append(block["text"])
                    elif isinstance(block, str):
                        text_parts.append(block)
                response_text = "".join(text_parts)
            else:
                response_text = str(raw_content)
                
            success = True
            
            # Extract tool data to save to Neo4j as 'step_results'
            # (We look at the messages added during THIS turn, ignoring history)
            new_messages = result_state["messages"][len(lg_messages):]
            tool_outputs = []
            for msg in new_messages:
                if isinstance(msg, ToolMessage):
                    try:
                        tool_outputs.append({
                            "tool": msg.name,
                            "result": json.loads(msg.content) if msg.content.startswith('[') or msg.content.startswith('{') else msg.content
                        })
                    except Exception:
                        tool_outputs.append({"tool": msg.name, "result": msg.content})

        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            response_text = "I encountered an error trying to process that request."
            success = False
            tool_outputs = []
        finally:
            # Reset the ContextVar so it doesn't leak into any reuse of this thread
            if ctx_token is not None:
                spotify_user_ctx.reset(ctx_token)

        # Record the turn in our Python wrapper
        turn = Turn(
            query=query,
            rewritten_query=None, # Not used in LangGraph
            response=response_text,
            success=success,
            timestamp=time.time(),
            step_results=tool_outputs,
        )
        session["turns"].append(turn)
        session["last_active"] = time.time()

        return ChatResponse(
            session_id=session["session_id"],
            response=response_text,
            success=success,
            rewritten_query=None,
            turn_number=len(session["turns"]) - 1,
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID. If not in memory, load from Neo4j."""
        session = self._sessions.get(session_id)
        if not session and self._history_repo:
            db_session = self._history_repo.load_session(session_id)
            if db_session:
                self._sessions[session_id] = db_session
                session = db_session

        if session and self._is_expired(session):
            del self._sessions[session_id]
            return None
        return session

    def save_session_only(self, session_id: str, user_id: str = None) -> bool:
        """Save session to Neo4j WITHOUT evicting it from memory.
        Used by the REST save endpoint so navigating away doesn't destroy
        the in-memory session context while the WebSocket may still be alive."""
        session = self._sessions.get(session_id)
        if session and user_id and self._history_repo:
            return self._history_repo.save_session(user_id, session)
        return False

    def close_session(self, session_id: str, user_id: str = None) -> bool:
        """Evict session from memory and save to Neo4j. Called on true WS disconnect."""
        session = self._sessions.pop(session_id, None)
        if session and user_id and self._history_repo:
            self._history_repo.save_session(user_id, session)
        return session is not None

    def close(self):
        """Shut down the manager."""
        self._sessions.clear()
        if self._history_repo and self._history_repo.db:
            self._history_repo.db.close()

    # -- Private helpers --

    def _create_session(self, session_id: Optional[str] = None) -> Session:
        sid = session_id or str(uuid.uuid4())
        if session_id and self._history_repo:
            db_session = self._history_repo.load_session(sid)
            if db_session:
                self._sessions[sid] = db_session
                return db_session
                
        session = Session(
            session_id=sid,
            turns=[],
            created_at=time.time(),
            last_active=time.time(),
        )
        self._sessions[sid] = session
        return session

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s["last_active"]) > self._session_timeout
        ]
        for sid in expired:
            del self._sessions[sid]

    def _is_expired(self, session: Session) -> bool:
        return (time.time() - session["last_active"]) > self._session_timeout