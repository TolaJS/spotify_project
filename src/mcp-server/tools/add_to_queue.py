from mcp.types import Tool

ADD_TO_QUEUE_TOOL = Tool(
    name="add_to_queue",
    description="Add a track to the user's playback queue",
    inputSchema={
        "type": "object",
        "properties": {
            "track_uri": {
                "type": "string",
                "description": "The Spotify URI of the track to add to queue"
            }
        },
        "required": ["track_uri"]
    }
)
