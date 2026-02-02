from mcp.types import Tool

RECENTLY_PLAYED_TOOL = Tool(
    name="recently_played",
    description="Get the user's 50 most recently played tracks",
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "The number of recently played tracks to return",
                "minimum": 1,
                "maximum": 50,
                "default": 50
            }
        }
    }
)
