"""Spotify Worker Agent for LangGraph."""

import json
from langchain_core.tools import tool
from langchain.agents import create_agent

# Import prompts and configs
from ..prompts.spotify_prompts import SPOTIFY_WORKER_SYSTEM_PROMPT
from ..utils.config import get_gemini_llm

# We will dynamically import the spotify client to avoid circular/init issues
def get_client():
    from auth.oauth_handler import get_spotify_client
    return get_spotify_client()

@tool
def search_spotify(query: str, search_type: str = "track", limit: int = 5) -> str:
    """Search for content on Spotify.
    
    Args:
        query: The search term (e.g., track name, artist name)
        search_type: "track", "artist", or "album"
        limit: Number of results to return
    """
    sp = get_client()
    try:
        results = sp.search(q=query, type=search_type, limit=limit)
        formatted = []
        
        if search_type == "track":
            for item in results.get("tracks", {}).get("items", []):
                artists = ", ".join([a["name"] for a in item["artists"]])
                formatted.append({
                    "name": item["name"],
                    "artists": artists,
                    "album": item.get("album", {}).get("name"),
                    "album_type": item.get("album", {}).get("album_type"),
                    "release_date": item.get("album", {}).get("release_date"),
                    "uri": item["uri"]
                })
        elif search_type == "artist":
            for item in results.get("artists", {}).get("items", []):
                formatted.append({
                    "name": item["name"],
                    "genres": item.get("genres", []),
                    "uri": item["uri"]
                })
        elif search_type == "album":
            for item in results.get("albums", {}).get("items", []):
                artists = ", ".join([a["name"] for a in item["artists"]])
                # Fetch full track listing for this album
                try:
                    album_tracks = sp.album_tracks(item["id"], limit=50)
                    track_names = [t["name"] for t in album_tracks.get("items", [])]
                except Exception:
                    track_names = []
                formatted.append({
                    "name": item["name"],
                    "artists": artists,
                    "release_date": item.get("release_date"),
                    "total_tracks": item.get("total_tracks"),
                    "tracks": track_names,
                    "uri": item["uri"]
                })
                
        return json.dumps(formatted, indent=2)
    except Exception as e:
        return f"Error searching Spotify: {str(e)}"

@tool
def add_to_queue(
    track: str = None,
    artist: str = None,
) -> str:
    """Search for a track and add it to the user's playback queue.

    Args:
        track: Track name to search for.
        artist: Artist name to narrow the search.
    """
    sp = get_client()
    try:
        query_parts = []
        if track:
            query_parts.append(f'track:"{track}"')
        if artist:
            query_parts.append(f'artist:"{artist}"')
        query = " ".join(query_parts)

        if not query:
            return "Error: provide at least a track name to queue."

        results = sp.search(q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])

        if not items:
            return f"No track found for query: '{query}'."

        uri = items[0]["uri"]
        label = items[0]["name"]

        sp.add_to_queue(uri)
        return f"Successfully added '{label}' to queue."
    except Exception as e:
        return f"Error adding to queue. Ensure Spotify is open and active on a device. Error: {str(e)}"

@tool
def start_playback(
    search_type: str = None,
    track: str = None,
    artist: str = None,
    album: str = None,
    uri: str = None,
    offset: int = None,
) -> str:
    """Start playing a track, album, or artist on the user's active device.
    Searches for the content first unless a URI is directly provided.

    Args:
        search_type: What to search for — "track", "album", or "artist". Required unless uri is provided.
        track: Track name to include in the search query.
        artist: Artist name to include in the search query.
        album: Album name to include in the search query.
        uri: Optional. A known Spotify URI to play directly, skipping the search.
        offset: Optional. Zero-based track position to start playback from within a context (album/playlist). E.g. 2 starts from the 3rd track.
    """
    sp = get_client()
    try:
        if not uri:
            if not search_type:
                return "Error: provide either a uri or a search_type to start playback."

            # Build Spotify field-filtered query
            query_parts = []
            if track:
                query_parts.append(f'track:"{track}"')
            if artist:
                query_parts.append(f'artist:"{artist}"')
            if album:
                query_parts.append(f'album:"{album}"')
            query = " ".join(query_parts)

            if not query:
                return "Error: provide at least one of track, artist, or album to search."

            results = sp.search(q=query, type=search_type, limit=1)

            if search_type == "track":
                items = results.get("tracks", {}).get("items", [])
            elif search_type == "artist":
                items = results.get("artists", {}).get("items", [])
            elif search_type == "album":
                items = results.get("albums", {}).get("items", [])
            else:
                return f"Error: unsupported search_type '{search_type}'. Use 'track', 'album', or 'artist'."

            if not items:
                return f"No {search_type} found for query: '{query}'."

            uri = items[0]["uri"]
            label = items[0]["name"]
        else:
            label = uri

        offset_param = {"position": offset} if offset is not None else None

        if "track" in uri:
            sp.start_playback(uris=[uri])
        else:
            sp.start_playback(context_uri=uri, offset=offset_param)

        return f"Successfully started playback for '{label}'."
    except Exception as e:
        return f"Error starting playback. Ensure Spotify is open and active on a device. Error: {str(e)}"

@tool
def currently_playing() -> str:
    """Check what is currently playing on the user's Spotify account."""
    sp = get_client()
    try:
        current = sp.current_playback()
        if not current or not current.get("item"):
            return "Nothing is currently playing on Spotify."
            
        track = current["item"]
        artists = ", ".join([a["name"] for a in track["artists"]])
        return json.dumps({
            "name": track["name"],
            "artists": artists,
            "is_playing": current["is_playing"],
            "device": current.get("device", {}).get("name", "Unknown")
        })
    except Exception as e:
        return f"Error checking playback: {str(e)}"

@tool
def create_playlist(name: str, description: str = "", public: bool = True) -> str:
    """Create a new playlist for the user.
    
    Args:
        name: Name of the playlist
        description: The playlist description
        public: Whether it is public
    """
    sp = get_client()
    try:
        user_id = sp.me()["id"]
        playlist = sp.user_playlist_create(
            user=user_id, name=name, public=public, description=description
        )
        return json.dumps({"status": "success", "id": playlist["id"], "uri": playlist["uri"]})
    except Exception as e:
        return f"Error creating playlist: {str(e)}"

@tool
def add_to_playlist(playlist_id: str, track_uris: list[str]) -> str:
    """Add a list of track URIs to a specific playlist.
    
    Args:
        playlist_id: The ID of the playlist
        track_uris: A list of Spotify track URIs
    """
    sp = get_client()
    try:
        sp.playlist_add_items(playlist_id=playlist_id, items=track_uris)
        return f"Successfully added {len(track_uris)} tracks to playlist."
    except Exception as e:
        return f"Error adding to playlist: {str(e)}"

@tool
def get_recently_played(limit: int = 20) -> str:
    """Fetch the user's most recently played tracks from Spotify (live, last 50 max).
    Use this for questions about what the user just listened to or played recently
    (e.g. 'what did I just play?', 'what was the last song?').
    Do NOT use this for historical analysis over weeks/months — use ask_bigquery_worker for that.

    Args:
        limit: Number of recent tracks to return (max 50).
    """
    sp = get_client()
    try:
        limit = max(1, min(limit, 50))
        response = sp.current_user_recently_played(limit=limit)
        items = response.get("items", [])
        if not items:
            return "No recently played tracks found."
        formatted = []
        for item in items:
            track = item["track"]
            artists = ", ".join(a["name"] for a in track["artists"])
            formatted.append({
                "name": track["name"],
                "artists": artists,
                "album": track.get("album", {}).get("name"),
                "played_at": item["played_at"],
                "uri": track["uri"],
            })
        return json.dumps(formatted, indent=2)
    except Exception as e:
        return f"Error fetching recently played: {str(e)}"


@tool
def set_playback_state(state: str) -> str:
    """Pause or resume the user's current Spotify playback.

    Args:
        state: "pause" to pause playback, "play" to resume playback.
    """
    sp = get_client()
    try:
        if state == "pause":
            sp.pause_playback()
            return "Playback paused."
        elif state == "play":
            sp.start_playback()
            return "Playback resumed."
        else:
            return f"Error: invalid state '{state}'. Use 'pause' or 'play'."
    except Exception as e:
        return f"Error updating playback state. Ensure Spotify is open and active on a device. Error: {str(e)}"


@tool
def skip_track(direction: str) -> str:
    """Skip to the next or previous track in the user's Spotify playback queue.

    Args:
        direction: "next" to skip forward, "previous" to go back.
    """
    sp = get_client()
    try:
        if direction == "next":
            sp.next_track()
            return "Skipped to next track."
        elif direction == "previous":
            sp.previous_track()
            return "Skipped to previous track."
        else:
            return f"Error: invalid direction '{direction}'. Use 'next' or 'previous'."
    except Exception as e:
        return f"Error skipping track. Ensure Spotify is open and active on a device. Error: {str(e)}"


@tool
def get_current_playlists(limit: int = 20) -> str:
    """Fetch the user's saved Spotify playlists with name, id, owner, playlist description,and total track count.
    Use this to list playlists or find a specific playlist by name before playing it. 

    Args:
        limit: Number of playlists per page (max 50). 20 are fetched automatically.
    """
    sp = get_client()
    try:
        limit = max(1, min(limit, 50))
        response = sp.current_user_playlists(limit=limit)
        playlists = response.get("items", [])
        while response.get("next"):
            response = sp.next(response)
            playlists.extend(response.get("items", []))
        if not playlists:
            return "No playlists found."

        formatted = []
        for playlist in playlists:
            formatted.append({
                "name": playlist["name"],
                "id": playlist["id"],
                "uri": playlist["uri"],
                "owner": playlist.get("owner", {}).get("display_name"),
                "description": playlist.get("description"),
                "total_tracks": playlist.get("tracks", {}).get("total"),
            })

        return json.dumps(formatted, indent=2)
    except Exception as e:
        return f"Error fetching playlists: {str(e)}"


@tool
def get_playlist_tracks(playlist_id: str, limit: int = 50) -> str:
    """Fetch the tracks inside a specific playlist by its ID.

    Args:
        playlist_id: The Spotify playlist ID (from get_current_playlists).
        limit: Max number of tracks to return (max 100). Fetches 50 by default
    """
    sp = get_client()
    try:
        limit = max(1, min(limit, 100))
        response = sp.playlist_tracks(
            playlist_id,
            fields="items(item(name,artists(name)))",
            limit=limit,
        )
        items = response.get("items", [])
        if not items:
            return "No tracks found in this playlist."

        tracks = [
            {
                "name": item["item"]["name"],
                "artists": ", ".join(a["name"] for a in item["item"]["artists"]),
            }
            for item in items
            if item.get("item")
        ]
        return json.dumps(tracks, indent=2)
    except Exception as e:
        return f"Error fetching playlist tracks: {str(e)}"


# Compile the Spotify Worker Graph
spotify_tools = [
    search_spotify,
    add_to_queue,
    start_playback,
    set_playback_state,
    skip_track,
    currently_playing,
    get_recently_played,
    create_playlist,
    add_to_playlist,
    get_current_playlists,
    get_playlist_tracks,
]

def build_spotify_worker():
    """Builds and returns the Spotify ReAct agent."""
    llm = get_gemini_llm(temperature=0)
    agent = create_agent(
        llm, 
        tools=spotify_tools,
        system_prompt=SPOTIFY_WORKER_SYSTEM_PROMPT
    )
    return agent