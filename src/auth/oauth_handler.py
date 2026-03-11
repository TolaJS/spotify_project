import json
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Optional

from spotipy import Spotify
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


def _cache_path_for(user_id: str) -> str:
    return f".spotify_cache_{user_id}"


class SpotifyOAuthHandler:
    """Reads Spotify credentials from env. Stateless — all per-user state
    lives in the module-level dicts above."""

    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
        self.scope = self._get_required_scopes()

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Missing Spotify credentials. Please set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET in your .env file."
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

    def build_oauth(self, cache_path: str, show_dialog: bool = False) -> SpotifyOAuth:
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_path=cache_path,
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
            "Attempting to load from cache file — user may need to re-authenticate."
        )
        handler = SpotifyOAuthHandler()
        cache_path = _cache_path_for(uid)
        if not os.path.exists(cache_path):
            raise ValueError(f"No token cache found for user {uid}. User must log in first.")
        _user_oauth[uid] = handler.build_oauth(cache_path)
        _user_clients[uid] = Spotify(auth_manager=_user_oauth[uid])

    return _user_clients[uid]


def store_user_token(user_id: str, token_info: dict) -> None:
    """Persist a freshly-obtained OAuth token and register the in-memory client.

    Called from the OAuth callback after the user completes Spotify login.
    """
    cache_path = _cache_path_for(user_id)
    with open(cache_path, 'w') as f:
        json.dump(token_info, f)

    handler = SpotifyOAuthHandler()
    _user_oauth[user_id] = handler.build_oauth(cache_path)
    _user_clients[user_id] = Spotify(auth_manager=_user_oauth[user_id])
    logger.info(f"Token stored and client registered for user {user_id}")


def revoke_user_token(user_id: str) -> None:
    """Delete the token cache file and clear in-memory state for a user (called on logout)."""
    cache_path = _cache_path_for(user_id)
    if os.path.exists(cache_path):
        os.remove(cache_path)
        logger.info(f"Removed token cache for user {user_id}")

    _user_oauth.pop(user_id, None)
    _user_clients.pop(user_id, None)
