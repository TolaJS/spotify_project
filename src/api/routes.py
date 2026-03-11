from fastapi import APIRouter, HTTPException, Request, Response, Cookie
from fastapi.responses import RedirectResponse
import logging
import os
import spotipy
from typing import Optional

from auth.oauth_handler import SpotifyOAuthHandler, store_user_token, revoke_user_token
from spotipy.oauth2 import SpotifyOAuth
from api.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Spotify AI Assistant API is running."}

@router.get("/chats/latest")
def get_latest_chat(exclude_id: Optional[str] = None, spotify_user_id: Optional[str] = Cookie(None)):
    """Returns the ID of the user's most recent chat session from Neo4j.

    Pass exclude_id to skip the session the user is currently on, so 'Previous Chat'
    always returns a genuinely different session.
    """
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not manager._history_repo:
        raise HTTPException(status_code=503, detail="Database not connected")

    session_id = manager._history_repo.get_latest_session_id(spotify_user_id, exclude_session_id=exclude_id)
    if not session_id:
        return {"session_id": None}

    return {"session_id": session_id}

@router.get("/chats/{session_id}")
def get_chat_history(session_id: str, spotify_user_id: Optional[str] = Cookie(None)):
    """Returns the full text history of a specific chat session for the frontend to render."""
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # Ask the manager to get it (which will load it from memory or Neo4j)
    session = manager.get_session(session_id)
    if not session:
        return {"turns": []}
        
    # We strip out the hidden 'step_results' context before sending to the frontend
    # because the React UI only needs to render the text strings, not the raw AI data.
    ui_turns = []
    for turn in session.get("turns", []):
        ui_turns.append({
            "query": turn["query"],
            "response": turn["response"],
            "timestamp": turn["timestamp"]
        })
        
    return {"turns": ui_turns}

@router.post("/chats/{session_id}/save")
def save_chat(session_id: str, spotify_user_id: Optional[str] = Cookie(None)):
    """Explicitly saves the current session to Neo4j without evicting it from memory.
    Used by the frontend when navigating away from a chat.
    The WebSocket disconnect handler is the only thing that should evict from memory.
    """
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    manager.save_session_only(session_id, user_id=spotify_user_id)
    return {"status": "saved"}

@router.get("/auth/status")
async def auth_status(request: Request):
    """Checks if the user has a valid session cookie."""
    user_id = request.cookies.get("spotify_user_id")
    if user_id:
        return {"authenticated": True, "user_id": user_id}
    return {"authenticated": False}

@router.get("/auth/url")
async def get_auth_url():
    """Returns the Spotify authorization URL for the frontend to redirect to."""
    try:
        handler = SpotifyOAuthHandler()
        sp_oauth = SpotifyOAuth(
            client_id=handler.client_id,
            client_secret=handler.client_secret,
            redirect_uri=handler.redirect_uri,
            scope=handler.scope,
            cache_path=".spotify_cache",
            show_dialog=True
        )
        auth_url = sp_oauth.get_authorize_url()
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"Auth URL error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/login")
async def login():
    """Redirects the user to Spotify for authentication."""
    try:
        handler = SpotifyOAuthHandler()
        sp_oauth = SpotifyOAuth(
            client_id=handler.client_id,
            client_secret=handler.client_secret,
            redirect_uri=handler.redirect_uri,
            scope=handler.scope,
            cache_path=".spotify_cache",
            show_dialog=True
        )
        auth_url = sp_oauth.get_authorize_url()
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
@router.get("/auth/callback")
async def callback(request: Request):
    """Handles the redirect from Spotify after login."""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing")

    try:
        handler = SpotifyOAuthHandler()

        # Use a temp cache path unique to this request so concurrent logins
        # don't overwrite each other. We'll move the token to the per-user
        # path once we know the user_id.
        import uuid
        tmp_cache = f".spotify_cache_tmp_{uuid.uuid4().hex}"
        try:
            sp_oauth = handler.build_oauth(tmp_cache, show_dialog=True)
            token_info = sp_oauth.get_access_token(code)
        finally:
            # Always clean up the temp file regardless of outcome
            if os.path.exists(tmp_cache):
                os.remove(tmp_cache)

        # Identify the user from their access token
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_info = sp.current_user()
        user_id = user_info.get('id')

        response = RedirectResponse(url="http://127.0.0.1:5173/?auth=success")

        if user_id:
            # Write the token to the per-user cache and register the in-memory client
            store_user_token(user_id, token_info)

            response.set_cookie(
                key="spotify_user_id",
                value=user_id,
                httponly=True,
                secure=False,  # Set to True in production with HTTPS
                samesite="lax",
                max_age=3600 * 24 * 7  # 7 days
            )
            logger.info(f"Authenticated user: {user_id}")

        return response
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return RedirectResponse(url="http://127.0.0.1:5173/?auth=error")

@router.post("/auth/logout")
async def logout(response: Response, spotify_user_id: Optional[str] = Cookie(None)):
    """Logs out the user by clearing their token cache and cookie."""
    if spotify_user_id:
        try:
            revoke_user_token(spotify_user_id)
        except Exception as e:
            logger.error(f"Error revoking token for user {spotify_user_id}: {e}")

    response.delete_cookie(
        key="spotify_user_id",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"status": "success", "message": "Logged out successfully"}

from api.websocket import chat_endpoint
router.add_api_websocket_route("/ws/chat", chat_endpoint)
