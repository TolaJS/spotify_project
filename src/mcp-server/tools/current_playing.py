from mcp.types import Tool

CURRENT_PLAYING_TOOL = Tool(
    name="current_playing",
    description="Get the currently playing track",
    inputSchema={
        "type": "object",
        "properties": {}
    }
)
