"""Conversation Manager - Stateful session wrapper around the Orchestrator."""

import json
import time
import uuid
from typing import Optional, Dict, List

from llm.orchestrator import Orchestrator
from chatbot.query_rewriter import QueryRewriter
from chatbot.schemas import Turn, Session, ChatResponse


class ConversationManager:
    """Manages multi-turn conversations with session state.

    Creates a single Orchestrator instance and reuses it across all sessions.
    Sessions are in-memory and ephemeral — lost on restart, cleared on close
    or after inactivity timeout.
    """

    # TODO change this to be dependant on user in-app activity, 
    # and 15 minutes may be too small.
    DEFAULT_TIMEOUT_SECONDS = 15 * 60  # 15 minutes

    def __init__(
        self,
        orchestrator: Orchestrator = None,
        rewriter: QueryRewriter = None,
        session_timeout: float = None,
    ):
        self._orchestrator = orchestrator or Orchestrator()
        self._rewriter = rewriter or QueryRewriter()
        self._session_timeout = session_timeout or self.DEFAULT_TIMEOUT_SECONDS
        self._sessions: Dict[str, Session] = {}

    def chat(self, query: str, session_id: Optional[str] = None) -> ChatResponse:
        """Process a user message within a session.

        Args:
            query: The user's message
            session_id: Existing session ID, or None to create a new session

        Returns:
            ChatResponse with response, session_id, and metadata
        """
        # Lazy cleanup of expired sessions
        self._cleanup_expired()

        # Resolve session
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
        else:
            session = self._create_session(session_id)

        # Rewrite if this is a follow-up turn (history exists)
        rewritten_query: Optional[str] = None
        query_for_orchestrator = query
        session_context: Optional[str] = None

        if session["turns"]:
            rewritten_query = self._rewriter.rewrite(query, session["turns"])
            query_for_orchestrator = rewritten_query
            session_context = self._format_session_context(session["turns"])

        # Execute via Orchestrator
        result = self._orchestrator.query(query_for_orchestrator, session_context=session_context)

        # Record the turn
        turn = Turn(
            query=query,
            rewritten_query=rewritten_query,
            response=result["response"],
            success=result["success"],
            timestamp=time.time(),
            step_results=result["details"]["step_results"],
        )
        session["turns"].append(turn)
        session["last_active"] = time.time()

        return ChatResponse(
            session_id=session["session_id"],
            response=result["response"],
            success=result["success"],
            rewritten_query=rewritten_query,
            turn_number=len(session["turns"]) - 1,
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID, or None if not found / expired."""
        session = self._sessions.get(session_id)
        if session and self._is_expired(session):
            del self._sessions[session_id]
            return None
        return session

    def close_session(self, session_id: str) -> bool:
        """Explicitly close and remove a session.

        Returns:
            True if the session existed and was removed
        """
        return self._sessions.pop(session_id, None) is not None

    def close(self):
        """Shut down the manager and its Orchestrator."""
        self._sessions.clear()
        self._orchestrator.close()

    # -- Private helpers --

    def _create_session(self, session_id: Optional[str] = None) -> Session:
        """Create a new session and store it."""
        sid = session_id or str(uuid.uuid4())
        session = Session(
            session_id=sid,
            turns=[],
            created_at=time.time(),
            last_active=time.time(),
        )
        self._sessions[sid] = session
        return session

    def _is_expired(self, session: Session) -> bool:
        """Check if a session has exceeded the inactivity timeout."""
        return (time.time() - session["last_active"]) > self._session_timeout

    def _format_session_context(self, turns: List[Turn]) -> Optional[str]:
        """Scan backwards through recent turns for the most recent graph_rag result with entity data.

        Produces a string in the same format as _get_context_for_step so that
        SpotifyAgent._try_direct_playback_from_context can extract URIs and skip
        the search + tool-selection LLM call on follow-up playback queries.

        Only graph_rag results are considered — they contain entity IDs (artist_id,
        spotify_id) that the fast path can parse. Spotify results (search output,
        playback confirmations) are skipped. A lookback limit of 3 turns ensures
        stale context from much earlier in the conversation isn't used.
        """
        for turn in reversed(turns[-3:]):
            for step in turn.get("step_results") or []:
                if (
                    step["route"] == "graph_rag"
                    and step["result"]["success"]
                    and step["result"].get("data")
                ):
                    data = step["result"]["data"]
                    interpretation = step["result"].get("interpretation", "")
                    context_parts = [f"Previous result: {interpretation}"]
                    context_parts.append(f"Data ({len(data)} total items):")
                    context_parts.append(json.dumps(data[:10], indent=2, default=str))
                    return "\n".join(context_parts)

        return None

    def _cleanup_expired(self):
        """Remove all expired sessions. Called lazily on each request."""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s["last_active"]) > self._session_timeout
        ]
        for sid in expired:
            del self._sessions[sid]
