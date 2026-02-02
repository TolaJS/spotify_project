from mcp.types import Tool

CREATE_PLAYLIST_TOOL = Tool(
    name="create_playlist",
    description="Create a new playlist on Spotify",
    inputSchema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the playlist to create"
            },
            "description": {
                "type": "string",
                "description": "Description of the playlist (optional)",
                "default": ""
            },
            "public": {
                "type": "boolean",
                "description": "Whether the playlist should be public",
                "default": True
            }
        },
        "required": ["name"]
    }
)
