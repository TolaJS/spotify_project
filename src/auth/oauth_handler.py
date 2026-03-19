import json
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Optional, Tuple

from spotipy import Spotify
from spotipy.cache_handler import CacheHandler, CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-request user context
# Set this to the Spotify user_id before invoking LangGraph so all Spotify
# tools know which user to act on behalf of without needing signature changes.
# ContextVar is safe under asyncio.to_thread — each thread gets its own copy.
# ---------------------------------------------------------------------------
current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)

# Per-user SpotifyOAuth and Spotify client instances, keyed by Spotify user_id.
# Avoids rebuilding on every tool call; cleared on logout.
_user_oauth: Dict[str, SpotifyOAuth] = {}
_user_clients: Dict[str, Spotify] = {}

# Maximum users allowed per Spotify app (Development Mode limit)
_MAX_USERS_PER_APP = 5


# ---------------------------------------------------------------------------
# Multi-app credential helpers
# ---------------------------------------------------------------------------

def get_app_credentials(app_index: int = 0) -> Tuple[str, str]:
    """Return (client_id, client_secret) for the given Spotify app index."""
    if app_index == 1:
        return (
            os.getenv("SPOTIFY_CLIENT_ID_1"),
            os.getenv("SPOTIFY_CLIENT_SECRET_1"),
        )
    return (
        os.getenv("SPOTIFY_CLIENT_ID"),
        os.getenv("SPOTIFY_CLIENT_SECRET"),
    )


def pick_app_index() -> int:
    """Return the index of the Spotify app that has capacity for a new user.

    Reads user assignments from Firestore. Prefers app 0; falls back to app 1
    if app 0 is at capacity. Raises ValueError if both apps are full.
    """
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        return 0  # local dev — always use app 0

    from google.cloud import firestore
    project_id = os.getenv("FIRESTORE_PROJECT_ID")
    database_id = os.getenv("FIRESTORE_DATABASE_ID", "tolajs-timber")
    db = firestore.Client(project=project_id, database=database_id)

    for idx in (0, 1):
        doc = db.collection("spotify_app_users").document(f"app_{idx}").get()
        count = len(doc.to_dict().get("user_ids", [])) if doc.exists else 0
        if count < _MAX_USERS_PER_APP:
            return idx

    raise ValueError("All Spotify apps are at capacity.")


def get_user_app_index(user_id: str) -> int:
    """Return the app index this user is assigned to, defaulting to 0."""
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        return 0

    from google.cloud import firestore
    project_id = os.getenv("FIRESTORE_PROJECT_ID")
    database_id = os.getenv("FIRESTORE_DATABASE_ID", "tolajs-timber")
    db = firestore.Client(project=project_id, database=database_id)

    for idx in (0, 1):
        doc = db.collection("spotify_app_users").document(f"app_{idx}").get()
        if doc.exists and user_id in doc.to_dict().get("user_ids", []):
            return idx

    return 0  # not yet assigned — default to app 0


def assign_user_to_app(user_id: str, app_index: int) -> None:
    """Record that this user belongs to the given Spotify app."""
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        return

    from google.cloud import firestore
    project_id = os.getenv("FIRESTORE_PROJECT_ID")
    database_id = os.getenv("FIRESTORE_DATABASE_ID", "tolajs-timber")
    db = firestore.Client(project=project_id, database=database_id)

    ref = db.collection("spotify_app_users").document(f"app_{app_index}")
    ref.set(
        {"user_ids": firestore.ArrayUnion([user_id])},
        merge=True,
    )
    logger.info(f"Assigned user {user_id} to Spotify app {app_index}")


def remove_user_from_app(user_id: str) -> None:
    """Remove a user from their assigned Spotify app (called on data deletion)."""
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        return

    from google.cloud import firestore
    project_id = os.getenv("FIRESTORE_PROJECT_ID")
    database_id = os.getenv("FIRESTORE_DATABASE_ID", "tolajs-timber")
    db = firestore.Client(project=project_id, database=database_id)

    for idx in (0, 1):
        ref = db.collection("spotify_app_users").document(f"app_{idx}")
        ref.set(
            {"user_ids": firestore.ArrayRemove([user_id])},
            merge=True,
        )


# ---------------------------------------------------------------------------
# Token cache — Firestore in production, file-based for local dev
# ---------------------------------------------------------------------------

class FirestoreCacheHandler(CacheHandler):
    """Stores Spotify OAuth tokens in Firestore under spotify_tokens/{user_id}.

    Used when FIRESTORE_PROJECT_ID env var is set (i.e. on Cloud Run).
    Falls back to CacheFileHandler locally.
    """

    def __init__(self, user_id: str):
        from google.cloud import firestore
        project_id = os.getenv("FIRESTORE_PROJECT_ID")
        database_id = os.getenv("FIRESTORE_DATABASE_ID", "tolajs-timber")
        self._doc = (
            firestore.Client(project=project_id, database=database_id) if project_id
            else firestore.Client(database=database_id)
        ).collection("spotify_tokens").document(user_id)

    def get_cached_token(self) -> Optional[dict]:
        snapshot = self._doc.get()
        return snapshot.to_dict() if snapshot.exists else None

    def save_token_to_cache(self, token_info: dict) -> None:
        self._doc.set(token_info)

    def delete(self) -> None:
        self._doc.delete()


def _cache_handler_for(user_id: str) -> CacheHandler:
    """Return Firestore handler in production, file handler for local dev."""
    if os.getenv("FIRESTORE_PROJECT_ID"):
        return FirestoreCacheHandler(user_id)
    return CacheFileHandler(cache_path=f".spotify_cache_{user_id}")


class SpotifyOAuthHandler:
    """Reads Spotify credentials from env. Stateless — all per-user state
    lives in the module-level dicts above."""

    def __init__(self, app_index: int = 0):
        self.client_id, self.client_secret = get_app_credentials(app_index)
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        self.scope = self._get_required_scopes()

        if not self.client_id or not self.client_secret:
            raise ValueError(
                f"Missing Spotify credentials for app {app_index}. "
                "Please set SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET in your environment."
            )

    def _get_required_scopes(self):
        return " ".join([
            "user-read-recently-played",
            "user-read-playback-state",
            "user-read-currently-playing",
            "user-modify-playback-state",
            "playlist-read-private",
            "playlist-read-collaborative",
            "playlist-modify-public",
            "playlist-modify-private",
            "user-library-read",
            "user-library-modify",
            "user-read-private",
        ])

    def build_oauth(self, cache_handler: CacheHandler, show_dialog: bool = False) -> SpotifyOAuth:
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_handler=cache_handler,
            open_browser=False,
            show_dialog=show_dialog,
        )

    def revoke_token(self):
        """Legacy single-file revoke kept for backwards compatibility."""
        cache = ".spotify_cache"
        if os.path.exists(cache):
            os.remove(cache)


def get_spotify_client(user_id: str = None) -> Spotify:
    """Return a Spotify client for the given user.

    Resolves identity in this order:
      1. user_id argument (explicit)
      2. current_user_id ContextVar (set by LangGraphOrchestrator before invoking agents)

    Raises ValueError if no user identity can be resolved.
    """
    uid = user_id or current_user_id.get()
    if not uid:
        raise ValueError(
            "No Spotify user_id available. Ensure the user is authenticated "
            "and current_user_id is set before invoking agents."
        )

    if uid not in _user_clients:
        logger.warning(
            f"No in-memory client for user {uid}. "
            "Attempting to load from cache — user may need to re-authenticate."
        )
        app_index = get_user_app_index(uid)
        handler = SpotifyOAuthHandler(app_index=app_index)
        cache_handler = _cache_handler_for(uid)
        if cache_handler.get_cached_token() is None:
            raise ValueError(f"No token cache found for user {uid}. User must log in first.")
        _user_oauth[uid] = handler.build_oauth(cache_handler)
        _user_clients[uid] = Spotify(auth_manager=_user_oauth[uid])

    return _user_clients[uid]


def store_user_token(user_id: str, token_info: dict, app_index: int = 0) -> None:
    """Persist a freshly-obtained OAuth token and register the in-memory client.

    Called from the OAuth callback after the user completes Spotify login.
    """
    cache_handler = _cache_handler_for(user_id)
    cache_handler.save_token_to_cache(token_info)

    handler = SpotifyOAuthHandler(app_index=app_index)
    _user_oauth[user_id] = handler.build_oauth(cache_handler)
    _user_clients[user_id] = Spotify(auth_manager=_user_oauth[user_id])
    logger.info(f"Token stored and client registered for user {user_id} (app {app_index})")


def revoke_user_token(user_id: str) -> None:
    """Delete the token cache and clear in-memory state for a user (called on logout)."""
    cache_handler = _cache_handler_for(user_id)
    cache_handler.delete()
    logger.info(f"Removed token cache for user {user_id}")

    _user_oauth.pop(user_id, None)
    _user_clients.pop(user_id, None)
