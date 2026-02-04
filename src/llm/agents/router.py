import json
import re
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import RouterState, SubQuery, ExecutionStep
from ..prompts.router_prompts import (
    QUERY_CLEANUP_PROMPT,
    MULTI_PART_DETECTION_PROMPT,
    QUERY_DECOMPOSITION_PROMPT,
    ROUTE_CLASSIFICATION_PROMPT,
)
from ..utils.config import get_llm


def parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks.

    Args:
        content: Raw LLM response that may contain ```json ... ``` blocks

    Returns:
        Parsed JSON as dict

    Raises:
        json.JSONDecodeError: If JSON parsing fails
    """
    # Strip markdown code blocks if present
    content = content.strip()
    if content.startswith("```"):
        # Remove opening ```json or ```
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        # Remove closing ```
        content = re.sub(r"\n?```\s*$", "", content)

    return json.loads(content)


class RouterAgent:
    """LangGraph-based router for Spotify queries.

    Routes queries to either:
    - graph_rag: Historical analysis via Neo4j
    - mcp: Live Spotify operations

    Handles multi-part queries by decomposing and routing each part.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the router graph."""
        graph = StateGraph(RouterState)

        # Add nodes
        graph.add_node("clean_query", self._clean_query)
        graph.add_node("detect_multi_part", self._detect_multi_part)
        graph.add_node("decompose_query", self._decompose_query)
        graph.add_node("classify_routes", self._classify_routes)
        graph.add_node("build_plan", self._build_execution_plan)

        # Set entry point
        graph.set_entry_point("clean_query")

        # Define edges
        graph.add_edge("clean_query", "detect_multi_part")
        graph.add_conditional_edges(
            "detect_multi_part",
            self._should_decompose,
            {"decompose": "decompose_query", "classify": "classify_routes"},
        )
        graph.add_edge("decompose_query", "classify_routes")
        graph.add_edge("classify_routes", "build_plan")
        graph.add_edge("build_plan", END)

        return graph.compile()

    def _clean_query(self, state: RouterState) -> dict:
        """Clean and normalize the user query."""
        prompt = QUERY_CLEANUP_PROMPT.format(query=state["original_query"])
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return {"cleaned_query": response.content.strip()}

    def _detect_multi_part(self, state: RouterState) -> dict:
        """Detect if query contains multiple independent parts."""
        prompt = MULTI_PART_DETECTION_PROMPT.format(query=state["cleaned_query"])
        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            result = parse_json_response(response.content)
            is_multi_part = result.get("is_multi_part", False)
        except json.JSONDecodeError:
            is_multi_part = False

        return {"is_multi_part": is_multi_part}

    def _decompose_query(self, state: RouterState) -> dict:
        """Decompose a multi-part query into sub-queries."""
        prompt = QUERY_DECOMPOSITION_PROMPT.format(query=state["cleaned_query"])
        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            result = parse_json_response(response.content)
            sub_queries = [
                SubQuery(
                    original_text=sq["text"],
                    cleaned_text=sq["text"],
                    route=None,
                    depends_on=sq.get("depends_on"),
                    context_needed=sq.get("context_needed"),
                )
                for sq in result.get("sub_queries", [])
            ]
        except json.JSONDecodeError:
            # Fallback: treat as single query
            sub_queries = [
                SubQuery(
                    original_text=state["cleaned_query"],
                    cleaned_text=state["cleaned_query"],
                    route=None,
                    depends_on=None,
                    context_needed=None,
                )
            ]

        return {"sub_queries": sub_queries}

    def _classify_routes(self, state: RouterState) -> dict:
        """Classify each query/sub-query to the appropriate system."""
        # If no sub_queries yet, create one from cleaned_query
        sub_queries = state.get("sub_queries") or [
            SubQuery(
                original_text=state["cleaned_query"],
                cleaned_text=state["cleaned_query"],
                route=None,
                depends_on=None,
                context_needed=None,
            )
        ]

        classified = []
        for sq in sub_queries:
            prompt = ROUTE_CLASSIFICATION_PROMPT.format(
                query=sq["cleaned_text"],
                context=sq.get("context_needed") or "None",
            )
            response = self.llm.invoke([HumanMessage(content=prompt)])

            try:
                result = parse_json_response(response.content)
                route = result.get("route", "graph_rag")
            except json.JSONDecodeError:
                route = "graph_rag"  # Default fallback

            classified.append(
                SubQuery(
                    original_text=sq["original_text"],
                    cleaned_text=sq["cleaned_text"],
                    route=route,
                    depends_on=sq.get("depends_on"),
                    context_needed=sq.get("context_needed"),
                )
            )

        return {"sub_queries": classified}

    def _build_execution_plan(self, state: RouterState) -> dict:
        """Build an ordered execution plan from classified sub-queries."""
        sub_queries = state["sub_queries"]

        # Topological sort based on dependencies
        plan = []
        executed = set()

        while len(executed) < len(sub_queries):
            for i, sq in enumerate(sub_queries):
                if i in executed:
                    continue

                dep = sq.get("depends_on")
                if dep is None or dep in executed:
                    plan.append(
                        ExecutionStep(
                            step=len(plan),
                            query=sq["cleaned_text"],
                            route=sq["route"],
                            depends_on=dep,
                            context_needed=sq.get("context_needed"),
                        )
                    )
                    executed.add(i)

        return {"execution_plan": plan, "current_step": 0}

    def _should_decompose(self, state: RouterState) -> str:
        """Conditional edge: route to decompose or directly to classify."""
        return "decompose" if state["is_multi_part"] else "classify"

    def route(self, query: str) -> RouterState:
        """Route a user query through the graph.

        Args:
            query: Raw user input

        Returns:
            RouterState with execution_plan populated
        """
        initial_state: RouterState = {
            "original_query": query,
            "cleaned_query": "",
            "is_multi_part": False,
            "sub_queries": [],
            "execution_plan": [],
            "current_step": 0,
            "intermediate_results": {},
            "final_response": None,
        }
        return self.graph.invoke(initial_state)


def create_router(llm=None) -> RouterAgent:
    """Factory function to create a RouterAgent.

    Args:
        llm: Optional LLM instance to use

    Returns:
        Configured RouterAgent
    """
    return RouterAgent(llm=llm)
