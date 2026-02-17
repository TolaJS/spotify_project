"""Spotify Agent - Handles live Spotify operations via tool calls."""

import json
import re
from typing import Optional
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import QueryResult, ToolCall
from ..prompts.spotify_prompts import (
    TOOL_DESCRIPTIONS,
    TOOL_SELECTION_PROMPT,
    MULTI_TOOL_PLANNING_PROMPT,
)
from ..utils.config import get_gemini_llm


def get_response_text(response) -> str:
    """Extract text content from LLM response, handling different formats."""
    content = response.content
    if isinstance(content, list):
        return "".join(
            part.get("text", str(part)) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)
    return json.loads(content)


class SpotifyAgent:
    """Agent for live Spotify operations.

    Flow:
    1. Select tool(s) from natural language query
    2. Execute tools sequentially
    3. After searches, plan follow-up actions if needed
    4. Return raw results (Synthesis agent handles interpretation)
    """

    def __init__(self, llm=None, spotify_client=None):
        self.llm = llm or get_gemini_llm()
        self._spotify_client = spotify_client

    def _get_spotify_client(self):
        """Lazy initialization of Spotify client."""
        if self._spotify_client is None:
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
            from auth.oauth_handler import get_spotify_client
            self._spotify_client = get_spotify_client()
        return self._spotify_client

    # -- LLM calls --

    def _select_tools(self, query: str, context: str = None) -> tuple[list[ToolCall], str]:
        """Select tools based on the natural language query.

        Returns:
            Tuple of (selected_tools, error_message)
        """
        prompt = TOOL_SELECTION_PROMPT.format(
            tool_descriptions=TOOL_DESCRIPTIONS,
            query=query,
            context=context or "None",
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            tools = [
                ToolCall(
                    name=t.get("name", ""),
                    arguments=t.get("arguments", {}),
                    reason=t.get("reason"),
                )
                for t in result.get("tools", [])
            ]
            return tools, None
        except json.JSONDecodeError:
            return [], f"Failed to parse tool selection: {response_text[:200]}"

    def _plan_next_tool(self, query: str, context: str, tool_results: list) -> tuple[ToolCall | None, str]:
        """Ask the LLM to plan a follow-up tool based on previous results.

        Returns:
            Tuple of (next_tool_or_None, error_message)
        """
        prompt = MULTI_TOOL_PLANNING_PROMPT.format(
            query=query,
            context=context or "None",
            previous_results=json.dumps(tool_results, indent=2),
            tool_descriptions=TOOL_DESCRIPTIONS,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            tool_info = result.get("tool", {})

            if result.get("is_final") or tool_info.get("name") == "none":
                return None, None

            return ToolCall(
                name=tool_info.get("name", ""),
                arguments=tool_info.get("arguments", {}),
                reason=result.get("explanation"),
            ), None
        except json.JSONDecodeError:
            return None, f"Failed to plan next tool: {response_text[:200]}"

    # -- Tool execution --

    def _execute_tool(self, tool: ToolCall) -> dict:
        """Execute a single tool and return a result dict."""
        try:
            result = self._call_tool(tool["name"], tool["arguments"])
            return {
                "tool": tool["name"],
                "arguments": tool["arguments"],
                "result": result,
                "success": True,
            }
        except Exception as e:
            return {
                "tool": tool["name"],
                "arguments": tool["arguments"],
                "result": str(e),
                "success": False,
            }

    def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return its result."""
        sp = self._get_spotify_client()

        handlers = {
            "search_spotify": self._handle_search,
            "create_playlist": self._handle_create_playlist,
            "add_to_playlist": self._handle_add_to_playlist,
            "get_playlists": self._handle_get_playlists,
            "recently_played": self._handle_recently_played,
            "current_playing": self._handle_current_playing,
            "add_to_queue": self._handle_add_to_queue,
            "start_playback": self._handle_start_playback,
        }

        handler = handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")
        return handler(sp, arguments)

    # -- Deterministic follow-up from search results --

    def _extract_uris_from_results(self, tool_results: list) -> list[str]:
        """Extract Spotify track URIs from search result strings."""
        uris = []
        for r in tool_results:
            if r.get("tool") == "search_spotify" and r.get("success"):
                found = re.findall(r"spotify:track:[a-zA-Z0-9]+", r.get("result", ""))
                if found:
                    uris.append(found[0])
        return uris

    def _try_deterministic_followup(self, query: str, context: str, tool_results: list) -> list[ToolCall]:
        """Build follow-up tool calls from search results without an LLM call.

        If the query implies an action (queue/playlist) and search results contain
        URIs, build the tool calls directly.
        """
        query_lower = query.lower()
        uris = self._extract_uris_from_results(tool_results)

        if not uris:
            return []

        if "queue" in query_lower:
            return [
                ToolCall(name="add_to_queue", arguments={"track_uri": uri}, reason=f"Queue track {uri}")
                for uri in uris
            ]

        if "playlist" in query_lower:
            playlist_id_match = re.search(
                r"(?:playlist[_ ]?(?:id|ID)[:\s]*)?([a-zA-Z0-9]{22})", context or ""
            )
            if playlist_id_match:
                return [
                    ToolCall(
                        name="add_to_playlist",
                        arguments={"playlist_id": playlist_id_match.group(1), "track_uris": uris},
                        reason="Add searched tracks to playlist",
                    )
                ]

        return []

    # -- Main query method --

    def _extract_spotify_ids_from_context(self, context: str) -> list[dict]:
        """Extract spotify_ids from Graph RAG context data.

        Parses the JSON data embedded in the context string and pulls out
        spotify_id (for tracks/albums) or id (for artists) along with names.

        Returns:
            List of dicts with 'uri' and 'name' for each item found.
        """
        if not context:
            return []

        # The context string contains JSON after "Data (N total items):"
        json_match = re.search(r"Data \(\d+ total items?\):\s*(\[.+)", context, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            return []

        items = []
        for record in data:
            # Track results have spotify_id and a track name
            spotify_id = record.get("spotify_id") or record.get("t.spotify_id")
            name = record.get("name") or record.get("t.name") or record.get("track")

            if spotify_id:
                # Determine URI type — default to track since that's the most
                # common case from Graph RAG queries
                if record.get("al.spotify_id") or record.get("album_type"):
                    uri = f"spotify:album:{spotify_id}"
                else:
                    uri = f"spotify:track:{spotify_id}"
                items.append({"uri": uri, "name": name or spotify_id})

        return items

    def _try_direct_playback_from_context(self, query: str, context: str) -> QueryResult | None:
        """Fast path: if context already has spotify_ids and the query implies
        playback, skip search entirely and play/queue directly.

        Returns:
            QueryResult if handled, None if this fast path doesn't apply.
        """
        query_lower = query.lower()

        # Only trigger for playback-related queries
        is_play = any(word in query_lower for word in ["play", "listen", "put on", "start"])
        is_queue = "queue" in query_lower
        if not is_play and not is_queue:
            return None

        items = self._extract_spotify_ids_from_context(context)
        if not items:
            return None

        # Build tool calls: for "play", first track gets start_playback and
        # the rest get add_to_queue. For "queue", all get add_to_queue.
        tool_results = []
        for i, item in enumerate(items):
            if is_play and i == 0:
                tool = ToolCall(name="start_playback", arguments={"uri": item["uri"]}, reason=f"Play {item['name']}")
            else:
                tool = ToolCall(name="add_to_queue", arguments={"track_uri": item["uri"]}, reason=f"Queue {item['name']}")
            tool_results.append(self._execute_tool(tool))

        success = all(r.get("success", False) for r in tool_results)
        interpretation = f"Played {len(tool_results)} track(s) directly from listening history."

        return QueryResult(
            success=success,
            data=tool_results,
            interpretation=interpretation,
            cypher_used=None,
        )

    def query(self, query: str, context: str = None) -> QueryResult:
        """Execute a natural language query for Spotify operations.

        Args:
            query: Natural language request
            context: Optional context from previous steps

        Returns:
            QueryResult with data and interpretation
        """
        # Fast path: if Graph RAG already gave us spotify_ids and the query
        # is about playing/queueing, skip search and LLM calls entirely
        direct_result = self._try_direct_playback_from_context(query, context)
        if direct_result is not None:
            return direct_result

        # Step 1: Select tools
        tools, error = self._select_tools(query, context)

        if error or not tools:
            return QueryResult(
                success=False,
                data=[],
                interpretation=error or "No tools selected",
                cypher_used=None,
            )

        # Step 2: Execute selected tools
        tool_results = []
        for tool in tools:
            tool_results.append(self._execute_tool(tool))

        # Step 3: If only searches were executed, plan follow-up actions
        only_searches = all(r.get("tool") == "search_spotify" for r in tool_results)

        if only_searches:
            # Try deterministic follow-up first (extract URIs + match query intent)
            followup_tools = self._try_deterministic_followup(query, context, tool_results)

            # Fall back to LLM planning if deterministic didn't produce anything.
            # Loop until the LLM says is_final — each iteration can return one
            # tool (e.g., start_playback for the first track, then add_to_queue
            # for each remaining track).
            if not followup_tools:
                max_followups = 10  # safety cap to avoid infinite loops
                for _ in range(max_followups):
                    next_tool, _ = self._plan_next_tool(query, context, tool_results)
                    if next_tool is None:
                        break
                    result = self._execute_tool(next_tool)
                    tool_results.append(result)
            else:
                # Execute deterministic follow-up tools
                for tool in followup_tools:
                    tool_results.append(self._execute_tool(tool))

        # Step 4: Return results
        success = all(r.get("success", False) for r in tool_results)
        interpretation = "No results." if not tool_results else f"Executed {len(tool_results)} tool(s)."

        return QueryResult(
            success=success,
            data=tool_results,
            interpretation=interpretation,
            cypher_used=None,
        )

    # -- Tool handlers --

    def _handle_search(self, sp, arguments: dict) -> str:
        """Handle search_spotify tool."""
        query = arguments.get("query")
        search_type = arguments.get("type", "track")
        limit = arguments.get("limit", 10)

        results = sp.search(q=query, type=search_type, limit=limit)

        if search_type == "track":
            items = results["tracks"]["items"]
            if not items:
                return f"No tracks found for '{query}'"

            output = f"Found {len(items)} track(s) for '{query}':\n"
            for i, track in enumerate(items, 1):
                artists = ", ".join([a["name"] for a in track["artists"]])
                output += f"{i}. {track['name']} by {artists}\n"
                output += f"   URI: {track['uri']}\n"
            return output

        elif search_type == "artist":
            items = results["artists"]["items"]
            if not items:
                return f"No artists found for '{query}'"

            output = f"Found {len(items)} artist(s) for '{query}':\n"
            for i, artist in enumerate(items, 1):
                output += f"{i}. {artist['name']}\n"
                output += f"   URI: {artist['uri']}\n"
            return output

        elif search_type == "album":
            items = results["albums"]["items"]
            if not items:
                return f"No albums found for '{query}'"

            output = f"Found {len(items)} album(s) for '{query}':\n"
            for i, album in enumerate(items, 1):
                artists = ", ".join([a["name"] for a in album["artists"]])
                output += f"{i}. {album['name']} by {artists}\n"
                output += f"   URI: {album['uri']}\n"
            return output

        return "Unknown search type"

    def _handle_create_playlist(self, sp, arguments: dict) -> str:
        """Handle create_playlist tool."""
        name = arguments.get("name")
        description = arguments.get("description", "")
        public = arguments.get("public", True)

        playlist = sp.user_playlist_create(
            sp.me()["id"], name, public=public, description=description
        )
        return f"Created playlist '{playlist['name']}' (ID: {playlist['id']})\nURI: {playlist['uri']}"

    def _handle_add_to_playlist(self, sp, arguments: dict) -> str:
        """Handle add_to_playlist tool."""
        playlist_id = arguments.get("playlist_id")
        track_uris = arguments.get("track_uris", [])

        sp.playlist_add_items(playlist_id, track_uris)
        return f"Added {len(track_uris)} track(s) to playlist {playlist_id}"

    def _handle_get_playlists(self, sp, arguments: dict) -> str:
        """Handle get_playlists tool."""
        limit = arguments.get("limit", 20)

        playlists = sp.current_user_playlists(limit=limit)

        if not playlists["items"]:
            return "No playlists found"

        output = f"Found {len(playlists['items'])} playlist(s):\n"
        for i, playlist in enumerate(playlists["items"], 1):
            output += f"{i}. {playlist['name']}\n"
            output += f"   Tracks: {playlist['tracks']['total']}\n"
            output += f"   ID: {playlist['id']}\n"
        return output

    def _handle_recently_played(self, sp, arguments: dict) -> str:
        """Handle recently_played tool."""
        limit = arguments.get("limit", 50)

        results = sp.current_user_recently_played(limit=limit)

        if not results["items"]:
            return "No recently played tracks found"

        output = f"Recently played ({len(results['items'])} tracks):\n"
        for i, item in enumerate(results["items"], 1):
            track = item["track"]
            artists = ", ".join([a["name"] for a in track["artists"]])
            output += f"{i}. {track['name']} by {artists}\n"
            output += f"   URI: {track['uri']}\n"
        return output

    def _handle_current_playing(self, sp, arguments: dict) -> str:
        """Handle current_playing tool."""
        currently_playing = sp.current_playback()

        if not currently_playing or not currently_playing.get("item"):
            return "No track currently playing"

        track = currently_playing["item"]
        artists = ", ".join([a["name"] for a in track["artists"]])
        is_playing = currently_playing["is_playing"]

        progress_ms = currently_playing["progress_ms"]
        duration_ms = track["duration_ms"]
        progress_min = progress_ms // 60000
        progress_sec = (progress_ms % 60000) // 1000
        duration_min = duration_ms // 60000
        duration_sec = (duration_ms % 60000) // 1000

        return (
            f"Currently {'playing' if is_playing else 'paused'}:\n"
            f"Track: {track['name']}\n"
            f"Artist(s): {artists}\n"
            f"Album: {track['album']['name']}\n"
            f"Progress: {progress_min}:{progress_sec:02d} / {duration_min}:{duration_sec:02d}\n"
            f"URI: {track['uri']}"
        )

    def _handle_add_to_queue(self, sp, arguments: dict) -> str:
        """Handle add_to_queue tool."""
        track_uri = arguments.get("track_uri")

        sp.add_to_queue(track_uri)
        return f"Added track to queue: {track_uri}"

    def _handle_start_playback(self, sp, arguments: dict) -> str:
        """Handle start_playback tool. Plays a track, album, artist, or playlist by URI."""
        uri = arguments.get("uri")

        # Tracks must be passed as a list via `uris`, everything else uses `context_uri`
        if uri.startswith("spotify:track:"):
            sp.start_playback(uris=[uri])
        else:
            sp.start_playback(context_uri=uri)

        return f"Started playback: {uri}"
