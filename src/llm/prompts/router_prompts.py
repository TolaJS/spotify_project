QUERY_CLEANUP_PROMPT = """You are a query normalizer for a Spotify music assistant.

Clean and normalize the following user query. Your tasks:
1. Fix spelling errors and typos
2. Expand abbreviations (e.g., "yr" -> "year", "rn" -> "right now")
3. Normalize time expressions (e.g., "last mo" -> "last month")
4. Remove filler words that don't add meaning
5. Keep the semantic meaning intact

Examples:
- "whats playin rn" -> "what is playing right now"
- "my top artist last yr" -> "my top artist last year"
- "um like who did i listen to most" -> "who did I listen to most"

User query: {query}

Respond with ONLY the cleaned query, nothing else."""


MULTI_PART_DETECTION_PROMPT = """You are analyzing a user query for a Spotify music assistant.

Determine if this query needs to be decomposed into multiple steps.

This assistant has TWO systems:
1. graph_rag - Historical analysis (top artists, listening trends, etc.)
2. mcp - Live Spotify operations (play, search, queue, playlists)

DECOMPOSE (is_multi_part = true) when:
- Multiple independent requests: "What's my top artist AND what's playing now"
- Cross-system operations: "Play my top song from last month" (needs graph_rag to find, mcp to play)
- Action on historical data: "Add my top 10 songs to a playlist" (find + action)
- Numbered/bulleted lists
- "First... then...", "After that..."

DO NOT decompose (is_multi_part = false) when:
- Pure historical query: "Who is my top artist in 2023"
- Pure live operation: "What's playing now", "Search for Taylor Swift"
- Complex but single-system: "Show artists I listened to in both 2022 and 2023"

Query: {query}

Respond with JSON only:
{{
    "is_multi_part": true or false,
    "reasoning": "brief explanation"
}}"""


QUERY_DECOMPOSITION_PROMPT = """You are decomposing a multi-part query for a Spotify music assistant.

Break down this query into individual sub-queries. For each sub-query, identify:
1. The specific request
2. Whether it depends on the result of another sub-query (use index, 0-based)

Query: {query}

Available operations:
- Historical analysis (graph_rag): listening patterns, top artists/songs/genres over time, comparisons across periods
- Live operations (mcp): current playback, search, playlist management, queue management

Examples:

Query: "How has my listening changed from 2021 to 2022, also what's my top artist in 2023?"
Output:
{{
    "sub_queries": [
        {{"text": "How has my listening changed from 2021 to 2022", "depends_on": null}},
        {{"text": "What is my top artist in 2023", "depends_on": null}}
    ]
}}

Query: "Play my top song from last month"
Output:
{{
    "sub_queries": [
        {{"text": "What is my top song from last month", "depends_on": null}},
        {{"text": "Play the song", "depends_on": 0, "context_needed": "track_uri"}}
    ]
}}

Respond with JSON only."""


ROUTE_CLASSIFICATION_PROMPT = """You are a router for a Spotify music assistant with two systems:

1. **graph_rag** - Historical analysis using Neo4j graph database
   - Listening history patterns and trends
   - Top artists/songs/genres over time periods
   - Year-over-year or month-over-month comparisons
   - Genre analysis and artist relationships
   - "How many times did I listen to X"
   - Any query requiring aggregation over historical data

2. **mcp** - Live Spotify operations via API
   - Current playback: "what's playing now"
   - Search Spotify catalog: "search for Taylor Swift"
   - Playlist management: create, add tracks, list playlists
   - Queue management: add to queue
   - Recently played (last 50 tracks only via API)
   - Any action that modifies Spotify state

Available MCP tools:
- search_spotify: Search for tracks, artists, or albums
- create_playlist: Create a new playlist
- add_to_playlist: Add tracks to a playlist
- get_playlists: Get user's playlists
- recently_played: Get last 50 played tracks
- current_playing: Get currently playing track
- add_to_queue: Add track to playback queue

Classify the following query:

Query: {query}
Context from previous step (if any): {context}

Respond with JSON only:
{{
    "route": "graph_rag" or "mcp",
    "reasoning": "brief explanation",
    "mcp_tool": "tool_name or null if graph_rag"
}}"""
