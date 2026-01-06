import os
from pathlib import Path
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)


class SpotifyOAuthHandler:
    """Handles Spotify OAuth authentication and token management."""

    def __init__(self):
        """Initialize the Spotify OAuth handler with credentials from environment variables."""
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback") #todo change this url when website is up.
        self.scope = self._get_required_scopes()

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Missing Spotify credentials. Please set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET in your .env file."
            )

        self.sp_oauth = None
        self.sp = None
        self._cache_path = None  # Store cache path for revocation

    def _get_required_scopes(self):
        """Define all required Spotify API scopes."""
        return " ".join([
            # Listening history
            "user-read-recently-played",
            "user-read-playback-state",
            "user-read-currently-playing",

            # Playback control
            "user-modify-playback-state",

            # Playlist management
            "playlist-read-private",
            "playlist-read-collaborative",
            "playlist-modify-public",
            "playlist-modify-private",

            # Library
            "user-library-read",
            "user-library-modify",

            # User data
            "user-read-private"
        ])

    def authenticate(self, cache_path=".spotify_cache"):
        """ Authenticate with Spotify and create a Spotify client. """
        self._cache_path = cache_path  # Store for later use
        self.sp_oauth = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_path=cache_path,
            open_browser=True
        )

        #Get cached token or prompt for new authentication
        token_info = self.sp_oauth.get_cached_token()

        if not token_info:
            # No cached token, need to authenticate
            auth_url = self.sp_oauth.get_authorize_url()
            print(f"Please navigate to this URL to authorize the application:\n{auth_url}")

            response = input("Enter the URL you were redirected to: ")
            code = self.sp_oauth.parse_response_code(response)
            token_info = self.sp_oauth.get_access_token(code)

        #create Spotify client with the token
        self.sp = Spotify(auth=token_info['access_token'])
        return self.sp

    def get_spotify_client(self, cache_path=".spotify_cache"):
        """Get an authenticated Spotify client, refreshing token if needed."""
        self._cache_path = cache_path  # Store for later use
        if not self.sp_oauth:
            return self.authenticate(cache_path)

        # to check if token needs refresh
        token_info = self.sp_oauth.get_cached_token()

        if not token_info:
            return self.authenticate(cache_path)

        # refresh token if expired
        if self.sp_oauth.is_token_expired(token_info):
            token_info = self.sp_oauth.refresh_access_token(token_info['refresh_token'])

        self.sp = Spotify(auth=token_info['access_token'])
        return self.sp

    def revoke_token(self):
        """Revoke the current access token and clear cache."""
        if self._cache_path and os.path.exists(self._cache_path):
            os.remove(self._cache_path)
            print(f"Token cache cleared: {self._cache_path}")
        self.sp = None
        self.sp_oauth = None
        self._cache_path = None


_oauth_handler = None


def get_spotify_client(cache_path=".spotify_cache"):
    global _oauth_handler

    if _oauth_handler is None:
        _oauth_handler = SpotifyOAuthHandler()

    return _oauth_handler.get_spotify_client(cache_path)


def create_new_spotify_client(cache_path=".spotify_cache"):
    handler = SpotifyOAuthHandler()
    return handler.authenticate(cache_path)
