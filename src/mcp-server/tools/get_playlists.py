from mcp.types import Tool

GET_PLAYLISTS_TOOL = Tool(
    name="get_playlists",
    description="Get the current user's playlists",
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "The maximum number of playlists to return",
                "minimum": 1,
                "maximum": 50,
                "default": 20
            }
        }
    }
)
