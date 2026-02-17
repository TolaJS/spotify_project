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
2. spotify - Live Spotify operations (play, search, queue, playlists)

DECOMPOSE (is_multi_part = true) when:
- Multiple independent requests: "What's my top artist AND what's playing now"
- Cross-system operations: "Play my top song from last month" (needs graph_rag to find, spotify to play)
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
- Live operations (spotify): current playback, search, playlist management, queue management

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

2. **spotify** - Live Spotify operations via API
   - Current playback: "what's playing now"
   - Search Spotify catalog: "search for Taylor Swift"
   - Playlist management: create, add tracks, list playlists
   - Queue management: add to queue
   - Recently played (last 50 tracks only via API)
   - Any action that modifies Spotify state

Available Spotify tools:
- search_spotify: Search for tracks, artists, or albums
- create_playlist: Create a new playlist
- add_to_playlist: Add tracks to a playlist
- get_playlists: Get user's playlists
- recently_played: Get last 50 played tracks
- current_playing: Get currently playing track
- add_to_queue: Add track to playback queue
- start_playback: Start playing a track, album, artist, or playlist

Classify the following query:

Query: {query}
Context from previous step (if any): {context}

Respond with JSON only:
{{
    "route": "graph_rag" or "spotify",
    "reasoning": "brief explanation",
    "spotify_tool": "tool_name or null if graph_rag"
}}"""


# Combined prompt for single LLM call routing
UNIFIED_ROUTER_PROMPT = """You are a router for a Spotify music assistant. Analyze the query and create an execution plan in ONE step.

## Available Systems

1. **graph_rag** - Historical analysis using Neo4j
   - Listening history, top artists/songs/genres, trends over time
   - Year/month comparisons, genre analysis
   - "How many times did I listen to X"

2. **spotify** - Live Spotify operations
   - current_playing: what's playing now
   - search_spotify: search for tracks/artists/albums
   - get_playlists: list user's playlists
   - create_playlist: create a new playlist
   - add_to_playlist: add tracks to playlist
   - add_to_queue: add track to queue
   - start_playback: play a track, album, artist, or playlist
   - recently_played: last 50 played tracks

## Task

Analyze this query and create an execution plan:

Query: {query}

## Rules

1. Clean the query (fix typos, expand abbreviations)
2. Determine if it needs multiple steps:
   - "What's my top artist AND what's playing" → 2 independent steps
   - "Play my top song from last month" → 2 dependent steps (find then play)
   - "Who is my top artist" → 1 step
3. For each step, assign the correct route and include spotify_tool if applicable
4. If step B needs data from step A, set depends_on to A's index

## Response Format (JSON only, no markdown):

{{
    "cleaned_query": "normalized query",
    "execution_plan": [
        {{
            "step": 0,
            "query": "the sub-query or full query",
            "route": "graph_rag" or "spotify",
            "spotify_tool": "tool_name or null",
            "depends_on": null or step_index,
            "context_needed": null or "what data is needed from dependency"
        }}
    ]
}}"""
