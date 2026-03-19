"""Chat history persistence backed by Firestore."""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SESSIONS_COLLECTION = "chat_sessions"


class HistoryRepository:
    """Manages chat session persistence in Firestore.

    Sessions are stored as documents in the `chat_sessions` collection.
    Document ID = session_id.
    """

    def __init__(self, firestore_client):
        self.db = firestore_client

    # ── Write ────────────────────────────────────────────────────────────────────

    def save_session(self, user_id: str, session: dict) -> bool:
        """Persist a full session (metadata + all turns) to Firestore."""
        try:
            turns = []
            for turn in session.get("turns", []):
                turns.append({
                    "query": turn["query"],
                    "rewritten_query": turn.get("rewritten_query"),
                    "response": turn["response"],
                    "success": turn["success"],
                    "timestamp": turn["timestamp"],
                    "step_results": json.dumps(turn.get("step_results") or []),
                })

            self.db.collection(_SESSIONS_COLLECTION).document(session["session_id"]).set({
                "user_id": user_id,
                "session_id": session["session_id"],
                "created_at": session["created_at"],
                "last_active": session["last_active"],
                "turns": turns,
            })
            logger.info("Saved session %s to Firestore for user %s", session["session_id"], user_id)
            return True
        except Exception as e:
            logger.error("Failed to save session to Firestore: %s", e)
            return False

    # ── Read ─────────────────────────────────────────────────────────────────────

    def load_session(self, session_id: str) -> Optional[dict]:
        """Load a session from Firestore. Returns None if not found."""
        try:
            doc = self.db.collection(_SESSIONS_COLLECTION).document(session_id).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            turns = []
            for t in data.get("turns", []):
                turns.append({
                    "query": t["query"],
                    "rewritten_query": t.get("rewritten_query"),
                    "response": t["response"],
                    "success": t["success"],
                    "timestamp": t["timestamp"],
                    "step_results": json.loads(t["step_results"]) if t.get("step_results") else None,
                })
            return {
                "session_id": data["session_id"],
                "user_id": data.get("user_id"),
                "created_at": data["created_at"],
                "last_active": data["last_active"],
                "turns": turns,
            }
        except Exception as e:
            logger.error("Failed to load session %s from Firestore: %s", session_id, e)
            return None

    def get_latest_session_id(self, user_id: str, exclude_session_id: str = None) -> Optional[str]:
        """Return the most recently active session ID for a user."""
        try:
            # Use a simple equality filter (no order_by) to avoid requiring a composite
            # Firestore index. Sorting by last_active is done in Python instead.
            docs = (
                self.db.collection(_SESSIONS_COLLECTION)
                .where("user_id", "==", user_id)
                .stream()
            )
            sessions = [doc.to_dict() for doc in docs]
            sessions.sort(key=lambda s: s.get("last_active", 0), reverse=True)
            for s in sessions:
                if s.get("session_id") != exclude_session_id:
                    return s.get("session_id")
            return None
        except Exception as e:
            logger.error("Failed to get latest session for user %s: %s", user_id, e)
            return None

    def get_user_settings(self, user_id: str) -> dict:
        """Return user settings from the `users` collection."""
        try:
            doc = self.db.collection("users").document(user_id).get()
            return doc.to_dict() or {} if doc.exists else {}
        except Exception as e:
            logger.error("Failed to get settings for user %s: %s", user_id, e)
            return {}

    # ── Delete ───────────────────────────────────────────────────────────────────

    def delete_user_sessions(self, user_id: str):
        """Delete all chat sessions for a user."""
        try:
            docs = (
                self.db.collection(_SESSIONS_COLLECTION)
                .where("user_id", "==", user_id)
                .stream()
            )
            for doc in docs:
                doc.reference.delete()
            logger.info("Deleted all Firestore sessions for user %s", user_id)
        except Exception as e:
            logger.error("Failed to delete sessions for user %s: %s", user_id, e)
            raise
