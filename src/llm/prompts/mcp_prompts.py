"""Prompts for the MCP Agent - Spotify live operations."""

TOOL_DESCRIPTIONS = """
## Available Spotify Tools

### search_spotify
Search for content on Spotify (tracks, artists, or albums).
Parameters:
- query (string, required): The search term
- type (string): "track", "artist", or "album" (default: "track")
- limit (integer): Number of results, 1-50 (default: 10)

### create_playlist
Create a new playlist on Spotify.
Parameters:
- name (string, required): The name of the playlist
- description (string): Description of the playlist (optional)
- public (boolean): Whether the playlist should be public (default: true)

### add_to_playlist
Add tracks to a Spotify playlist.
Parameters:
- playlist_id (string, required): The Spotify ID or URI of the playlist
- track_uris (array of strings, required): List of track URIs to add

### get_playlists
Get the user's playlists.
Parameters:
- limit (integer): Number of playlists to return, 1-50 (default: 20)

### recently_played
Get recently played tracks.
Parameters:
- limit (integer): Number of tracks to return, 1-50 (default: 50)

### current_playing
Get the currently playing track.
Parameters: None

### add_to_queue
Add a track to the user's playback queue.
Parameters:
- track_uri (string, required): The Spotify URI of the track to add
"""

TOOL_SELECTION_PROMPT = """You are a Spotify assistant that selects the appropriate tool(s) to fulfill user requests.

{tool_descriptions}

## Task

Given the user's request, determine which tool(s) to use and generate the arguments.

User request: {query}

Context from previous steps (if any): {context}

Respond with a JSON object:
{{
    "tools": [
        {{
            "name": "tool_name",
            "arguments": {{ "arg1": "value1", ... }},
            "reason": "brief explanation"
        }}
    ],
    "requires_search_first": true/false,
    "explanation": "overall plan explanation"
}}

Rules:
1. If the user wants to play/queue a song but doesn't provide a URI, you need to search first
2. For "add_to_queue", you need the track_uri - if not provided, search for it first
3. For "add_to_playlist", you need both playlist_id and track_uris
4. If multiple tools are needed, list them in execution order
5. Only output valid JSON, no markdown code blocks
"""

RESULT_INTERPRETATION_PROMPT = """You are interpreting results from Spotify API operations.

User's original request: {query}

Tool(s) executed: {tools_used}

Results:
{results}

Provide a natural, conversational response to the user based on these results. Include:
- Confirmation of what was done
- Relevant details (track names, artist names, playlist names, etc.)
- Any suggestions or follow-up actions if appropriate

Keep the response concise but helpful. If there was an error, explain what went wrong.

Response:"""

MULTI_TOOL_PLANNING_PROMPT = """You need to execute multiple Spotify operations to fulfill this request.

User request: {query}

Context so far: {context}

Previous results:
{previous_results}

{tool_descriptions}

Based on the previous results, determine the next tool call needed.

Respond with a JSON object:
{{
    "tool": {{
        "name": "tool_name",
        "arguments": {{ "arg1": "value1", ... }}
    }},
    "is_final": true/false,
    "explanation": "what this step accomplishes"
}}

Rules:
1. Use information from previous results (like track URIs from search results)
2. If the task is complete, set is_final to true and use "none" as the tool name
3. Only output valid JSON, no markdown code blocks
"""
