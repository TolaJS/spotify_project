"""MCP Agent - Handles live Spotify operations via tool calls."""

import json
import re
import asyncio
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import MCPState, QueryResult, ToolCall
from ..prompts.mcp_prompts import (
    TOOL_DESCRIPTIONS,
    TOOL_SELECTION_PROMPT,
    RESULT_INTERPRETATION_PROMPT,
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


class MCPAgent:
    """LangGraph-based agent for live Spotify operations.

    Uses Gemini to:
    1. Select appropriate tool(s) based on natural language query
    2. Generate tool arguments
    3. Execute tools via direct Spotify API calls
    4. Interpret results in natural language
    """

    def __init__(self, llm=None, spotify_client=None):
        """Initialize the MCP Agent.

        Args:
            llm: Optional LLM instance (defaults to Gemini)
            spotify_client: Optional Spotipy client (auto-initialized if not provided)
        """
        self.llm = llm or get_gemini_llm()
        self._spotify_client = spotify_client
        self.graph = self._build_graph()

    def _get_spotify_client(self):
        """Lazy initialization of Spotify client."""
        if self._spotify_client is None:
            import sys
            import os
            # Add auth module to path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
            from auth.oauth_handler import get_spotify_client
            self._spotify_client = get_spotify_client()
        return self._spotify_client

    def _build_graph(self) -> StateGraph:
        """Construct the MCP processing graph."""
        graph = StateGraph(MCPState)

        # Add nodes
        graph.add_node("select_tools", self._select_tools)
        graph.add_node("execute_tool", self._execute_tool)
        graph.add_node("plan_next_tool", self._plan_next_tool)
        graph.add_node("interpret_results", self._interpret_results)

        # Set entry point
        graph.set_entry_point("select_tools")

        # Define edges
        graph.add_conditional_edges(
            "select_tools",
            self._has_tools_to_execute,
            {"execute": "execute_tool", "interpret": "interpret_results"},
        )
        graph.add_conditional_edges(
            "execute_tool",
            self._should_continue,
            {"next_tool": "plan_next_tool", "interpret": "interpret_results"},
        )
        graph.add_conditional_edges(
            "plan_next_tool",
            self._has_next_tool,
            {"execute": "execute_tool", "interpret": "interpret_results"},
        )
        graph.add_edge("interpret_results", END)

        return graph.compile()

    def _select_tools(self, state: MCPState) -> dict:
        """Select tools based on the natural language query."""
        prompt = TOOL_SELECTION_PROMPT.format(
            tool_descriptions=TOOL_DESCRIPTIONS,
            query=state["query"],
            context=state.get("context") or "None",
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            tools = result.get("tools", [])

            selected_tools = [
                ToolCall(
                    name=t.get("name", ""),
                    arguments=t.get("arguments", {}),
                    reason=t.get("reason"),
                )
                for t in tools
            ]

            return {
                "selected_tools": selected_tools,
                "current_tool_index": 0,
                "requires_search_first": result.get("requires_search_first", False),
                "tool_results": [],
            }
        except json.JSONDecodeError:
            return {
                "selected_tools": [],
                "error": f"Failed to parse tool selection response: {response_text[:200]}",
            }

    def _execute_tool(self, state: MCPState) -> dict:
        """Execute the current tool."""
        tools = state.get("selected_tools", [])
        index = state.get("current_tool_index", 0)

        if index >= len(tools):
            return {"error": "No tool to execute"}

        tool = tools[index]
        tool_name = tool["name"]
        arguments = tool["arguments"]

        try:
            result = self._call_tool(tool_name, arguments)
            tool_results = state.get("tool_results", []).copy()
            tool_results.append({
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
                "success": True,
            })

            return {
                "tool_results": tool_results,
                "current_tool_index": index + 1,
                "error": None,
            }
        except Exception as e:
            tool_results = state.get("tool_results", []).copy()
            tool_results.append({
                "tool": tool_name,
                "arguments": arguments,
                "result": str(e),
                "success": False,
            })
            return {
                "tool_results": tool_results,
                "current_tool_index": index + 1,
                "error": str(e),
            }

    def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return its result."""
        sp = self._get_spotify_client()

        if tool_name == "search_spotify":
            return self._handle_search(sp, arguments)
        elif tool_name == "create_playlist":
            return self._handle_create_playlist(sp, arguments)
        elif tool_name == "add_to_playlist":
            return self._handle_add_to_playlist(sp, arguments)
        elif tool_name == "get_playlists":
            return self._handle_get_playlists(sp, arguments)
        elif tool_name == "recently_played":
            return self._handle_recently_played(sp, arguments)
        elif tool_name == "current_playing":
            return self._handle_current_playing(sp, arguments)
        elif tool_name == "add_to_queue":
            return self._handle_add_to_queue(sp, arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

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

    def _plan_next_tool(self, state: MCPState) -> dict:
        """Plan the next tool based on previous results."""
        prompt = MULTI_TOOL_PLANNING_PROMPT.format(
            query=state["query"],
            context=state.get("context") or "None",
            previous_results=json.dumps(state.get("tool_results", []), indent=2),
            tool_descriptions=TOOL_DESCRIPTIONS,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            tool_info = result.get("tool", {})

            if result.get("is_final") or tool_info.get("name") == "none":
                return {"selected_tools": state.get("selected_tools", [])}

            # Add the new tool to the list
            new_tool = ToolCall(
                name=tool_info.get("name", ""),
                arguments=tool_info.get("arguments", {}),
                reason=result.get("explanation"),
            )

            tools = state.get("selected_tools", []).copy()
            tools.append(new_tool)

            return {"selected_tools": tools}
        except json.JSONDecodeError:
            return {"error": f"Failed to plan next tool: {response_text[:200]}"}

    def _interpret_results(self, state: MCPState) -> dict:
        """Interpret tool results in natural language."""
        tool_results = state.get("tool_results", [])

        if not tool_results:
            return {
                "interpreted_response": "No operations were performed.",
                "result": QueryResult(
                    success=False,
                    data=[],
                    interpretation="No operations were performed.",
                    cypher_used=None,
                ),
            }

        # Format tools used
        tools_used = ", ".join([r["tool"] for r in tool_results])
        results_str = "\n\n".join([
            f"Tool: {r['tool']}\nArguments: {json.dumps(r['arguments'])}\nResult: {r['result']}"
            for r in tool_results
        ])

        prompt = RESULT_INTERPRETATION_PROMPT.format(
            query=state["query"],
            tools_used=tools_used,
            results=results_str,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response).strip()

        # Determine overall success
        success = all(r.get("success", False) for r in tool_results)

        return {
            "interpreted_response": response_text,
            "result": QueryResult(
                success=success,
                data=tool_results,
                interpretation=response_text,
                cypher_used=None,
            ),
        }

    def _has_tools_to_execute(self, state: MCPState) -> str:
        """Check if there are tools to execute."""
        tools = state.get("selected_tools", [])
        if tools and not state.get("error"):
            return "execute"
        return "interpret"

    def _should_continue(self, state: MCPState) -> str:
        """Check if we should continue with more tools."""
        tools = state.get("selected_tools", [])
        index = state.get("current_tool_index", 0)

        # If there are more pre-selected tools, continue
        if index < len(tools):
            return "next_tool"

        # If the last tool was a search and we might need follow-up, plan next
        tool_results = state.get("tool_results", [])
        if tool_results:
            last_result = tool_results[-1]
            if last_result.get("tool") == "search_spotify" and state.get("requires_search_first"):
                return "next_tool"

        return "interpret"

    def _has_next_tool(self, state: MCPState) -> str:
        """Check if planning produced a next tool."""
        tools = state.get("selected_tools", [])
        index = state.get("current_tool_index", 0)

        if index < len(tools):
            return "execute"
        return "interpret"

    def query(self, query: str, context: str = None) -> QueryResult:
        """Execute a natural language query for Spotify operations.

        Args:
            query: Natural language request (e.g., "play Bohemian Rhapsody")
            context: Optional context from previous steps

        Returns:
            QueryResult with data and interpretation
        """
        initial_state: MCPState = {
            "query": query,
            "context": context,
            "selected_tools": [],
            "current_tool_index": 0,
            "requires_search_first": False,
            "tool_results": [],
            "interpreted_response": "",
            "error": None,
            "retry_count": 0,
            "result": None,
        }

        final_state = self.graph.invoke(initial_state)

        if final_state.get("result"):
            return final_state["result"]

        return QueryResult(
            success=False,
            data=[],
            interpretation=final_state.get("error") or "Query failed",
            cypher_used=None,
        )


def create_mcp_agent(llm=None, spotify_client=None) -> MCPAgent:
    """Factory function to create an MCPAgent.

    Args:
        llm: Optional LLM instance (defaults to Gemini)
        spotify_client: Optional Spotipy client

    Returns:
        Configured MCPAgent
    """
    return MCPAgent(llm=llm, spotify_client=spotify_client)
