from mcp.types import Tool

SEARCH_TOOL = Tool(
    name="search_spotify",
    description="Search for content on Spotify (tracks, artists, or albums)",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search term (song name, artist name, or album title.)"
            },
            "type": {
                "type": "string",
                "enum": ["track", "artist", "album"],
                "default": "track",
                "description": "What type of content to search for"
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "description": "Number of results to return"
            }
        },
        "required": ["query"]
    }
)

