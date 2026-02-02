from mcp.server import Server
from mcp.types import Tool, TextContent
from formats import *
from mcp.server.stdio import stdio_server
from tools.search_spotify import SEARCH_TOOL
from tools.create_playlist import CREATE_PLAYLIST_TOOL
from tools.add_to_playlist import ADD_TO_PLAYLIST_TOOL
from tools.get_playlists import GET_PLAYLISTS_TOOL
from tools.recently_played import RECENTLY_PLAYED_TOOL
from tools.current_playing import CURRENT_PLAYING_TOOL
from tools.add_to_queue import ADD_TO_QUEUE_TOOL
import sys
import os
# TODO add logging feature
# TODO add improved error handling: specific SpotifyException handling (429 rate limit, 401 auth, 404 not found), input validation for required fields
# TODO add parent directory to path to import auth module
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from auth.oauth_handler import get_spotify_client

# initialize spotify client
sp = get_spotify_client()

# server initialisation
server = Server("chatbot_mcp")

# lists the tools available
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        SEARCH_TOOL,
        CREATE_PLAYLIST_TOOL,
        ADD_TO_PLAYLIST_TOOL,
        GET_PLAYLISTS_TOOL,
        RECENTLY_PLAYED_TOOL,
        CURRENT_PLAYING_TOOL,
        ADD_TO_QUEUE_TOOL
    ]

# executes the tools and routes the calls
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_spotify":
        return await handle_search_tool(arguments)
    elif name == "create_playlist":
        return await handle_create_playlist(arguments)
    elif name == "add_to_playlist":
        return await handle_add_to_playlist(arguments)
    elif name == "get_playlists":
        return await handle_get_playlists(arguments)
    elif name == "recently_played":
        return await handle_recently_played(arguments)
    elif name == "current_playing":
        return await handle_current_playing(arguments)
    elif name == "add_to_queue":
        return await handle_add_to_queue(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")

# handler calls the api
async def handle_search_tool(arguments: dict) -> list[TextContent]:
    """Handle the search_spotify tool call."""
    query = arguments.get("query")
    search_type = arguments.get("type", "track")
    limit = arguments.get("limit", 10)

    try:
        results = sp.search(q=query, type=search_type, limit=limit)

        if search_type == "track":
            items = results["tracks"]["items"]
            return format_tracks(items, query)
        elif search_type == "artist":
            items = results["artists"]["items"]
            return format_artists(items, query)
        elif search_type == "album":
            items = results["albums"]["items"]
            return format_albums(items, query)

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_create_playlist(arguments: dict) -> list[TextContent]:
    """Handle the create_playlist tool call."""
    name = arguments.get("name")
    description = arguments.get("description", "")
    public = arguments.get("public", True)

    try:
        playlist = sp.user_playlist_create(sp.me()["id"], name, public=public, description=description)
        return [TextContent(
            type="text",
            text=f"Created playlist '{playlist['name']}' (ID: {playlist['id']})\nURI: {playlist['uri']}"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_add_to_playlist(arguments: dict) -> list[TextContent]:
    """Handle the add_to_playlist tool call."""
    playlist_id = arguments.get("playlist_id")
    track_uris = arguments.get("track_uris")

    try:
        sp.playlist_add_items(playlist_id, track_uris)
        return [TextContent(
            type="text",
            text=f"Added {len(track_uris)} track(s) to playlist {playlist_id}"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_get_playlists(arguments: dict) -> list[TextContent]:
    """Handle the get_playlists tool call."""
    limit = arguments.get("limit", 20)

    try:
        playlists = sp.current_user_playlists(limit=limit)

        if not playlists["items"]:
            return [TextContent(type="text", text="No playlists found")]

        text = f"Found {len(playlists['items'])} playlist(s):\n\n"
        for i, playlist in enumerate(playlists["items"], 1):
            text += f"{i}. {playlist['name']}\n"
            text += f"   Tracks: {playlist['tracks']['total']}\n"
            text += f"   Owner: {playlist['owner']['display_name']}\n"
            text += f"   ID: {playlist['id']}\n"
            text += f"   URI: {playlist['uri']}\n\n"

        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_recently_played(arguments: dict) -> list[TextContent]:
    """Handle the recently_played tool call."""
    limit = arguments.get("limit", 50)

    try:
        results = sp.current_user_recently_played(limit=limit)

        if not results["items"]:
            return [TextContent(type="text", text="No recently played tracks found")]

        text = f"Recently played ({len(results['items'])} tracks):\n\n"
        for i, item in enumerate(results["items"], 1):
            track = item["track"]
            artists = ", ".join([a["name"] for a in track["artists"]])
            played_at = item["played_at"]

            text += f"{i}. {track['name']}\n"
            text += f"   Artist(s): {artists}\n"
            text += f"   Played at: {played_at}\n"
            text += f"   URI: {track['uri']}\n\n"

        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_current_playing(arguments: dict) -> list[TextContent]:
    """Handle the current_playing tool call."""
    try:
        currently_playing = sp.current_playback()

        if not currently_playing or not currently_playing.get("item"):
            return [TextContent(type="text", text="No track currently playing")]

        track = currently_playing["item"]
        artists = ", ".join([a["name"] for a in track["artists"]])
        progress_ms = currently_playing["progress_ms"]
        duration_ms = track["duration_ms"]
        is_playing = currently_playing["is_playing"]

        progress_min = progress_ms // 60000
        progress_sec = (progress_ms % 60000) // 1000
        duration_min = duration_ms // 60000
        duration_sec = (duration_ms % 60000) // 1000

        text = f"Currently {'playing' if is_playing else 'paused'}:\n\n"
        text += f"Track: {track['name']}\n"
        text += f"Artist(s): {artists}\n"
        text += f"Album: {track['album']['name']}\n"
        text += f"Progress: {progress_min}:{progress_sec:02d} / {duration_min}:{duration_sec:02d}\n"
        text += f"URI: {track['uri']}"

        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_add_to_queue(arguments: dict) -> list[TextContent]:
    """Handle the add_to_queue tool call."""
    track_uri = arguments.get("track_uri")

    try:
        sp.add_to_queue(track_uri)
        return [TextContent(type="text", text=f"Added track to queue: {track_uri}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Main entry point to run the MCP server."""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
