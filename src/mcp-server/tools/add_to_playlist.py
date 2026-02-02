from mcp.types import Tool

ADD_TO_PLAYLIST_TOOL = Tool(
    name="add_to_playlist",
    description="Add tracks to a Spotify playlist",
    inputSchema={
        "type": "object",
        "properties": {
            "playlist_id": {
                "type": "string",
                "description": "The Spotify ID or URI of the playlist"
            },
            "track_uris": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of track URIs to add to the playlist"
            }
        },
        "required": ["playlist_id", "track_uris"]
    }
)
