"""Graph RAG Agent - Queries Neo4j for historical Spotify listening data."""

import json
import re
from typing import Optional, Any
from neo4j import GraphDatabase
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import GraphRAGState, QueryResult
from ..prompts.graph_rag_prompts import (
    SCHEMA_DESCRIPTION,
    CYPHER_GENERATION_PROMPT,
    RESULT_INTERPRETATION_PROMPT,
    QUERY_REFINEMENT_PROMPT,
)
from ..utils.config import get_gemini_llm, get_neo4j_config


def get_response_text(response) -> str:
    """Extract text content from LLM response, handling different formats.

    Gemini may return content as a list of parts, while OpenAI returns a string.
    """
    content = response.content
    if isinstance(content, list):
        # Gemini format: list of content parts
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


class GraphRAGAgent:
    """LangGraph-based agent for querying Spotify listening history via Neo4j.

    Uses Gemini to:
    1. Generate Cypher queries from natural language
    2. Execute queries against Neo4j
    3. Interpret results in natural language
    """

    def __init__(self, llm=None, neo4j_config: dict = None):
        self.llm = llm or get_gemini_llm()
        self.neo4j_config = neo4j_config or get_neo4j_config()
        self._driver = None
        self.graph = self._build_graph()

    def _get_driver(self):
        """Lazy initialization of Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.neo4j_config["uri"],
                auth=(self.neo4j_config["user"], self.neo4j_config["password"]),
            )
        return self._driver

    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def _build_graph(self) -> StateGraph:
        """Construct the Graph RAG processing graph."""
        graph = StateGraph(GraphRAGState)

        # Add nodes
        graph.add_node("generate_cypher", self._generate_cypher)
        graph.add_node("execute_query", self._execute_query)
        graph.add_node("interpret_results", self._interpret_results)
        graph.add_node("refine_query", self._refine_query)

        # Set entry point
        graph.set_entry_point("generate_cypher")

        # Define edges
        graph.add_edge("generate_cypher", "execute_query")
        graph.add_conditional_edges(
            "execute_query",
            self._should_refine,
            {"refine": "refine_query", "interpret": "interpret_results"},
        )
        graph.add_edge("refine_query", "execute_query")
        graph.add_edge("interpret_results", END)

        return graph.compile()

    def _generate_cypher(self, state: GraphRAGState) -> dict:
        """Generate Cypher query from natural language."""
        prompt = CYPHER_GENERATION_PROMPT.format(
            schema=SCHEMA_DESCRIPTION,
            query=state["query"],
            context=state.get("context") or "None",
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            return {
                "cypher_query": result.get("cypher", ""),
                "query_explanation": result.get("explanation", ""),
                "return_type": result.get("return_type", "list"),
            }
        except json.JSONDecodeError:
            return {
                "cypher_query": "",
                "error": f"Failed to parse Cypher generation response: {response_text[:200]}",
                "retry_count": state.get("retry_count", 0) + 1,
            }

    def _execute_query(self, state: GraphRAGState) -> dict:
        """Execute the Cypher query against Neo4j."""
        cypher = state.get("cypher_query", "")
        if not cypher:
            return {
                "raw_results": [],
                "error": state.get("error") or "No Cypher query generated",
            }

        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run(cypher)
                records = [record.data() for record in result]

            return {
                "raw_results": records,
                "error": None,
            }
        except Exception as e:
            return {
                "raw_results": [],
                "error": str(e),
            }

    def _interpret_results(self, state: GraphRAGState) -> dict:
        """Interpret query results in natural language."""
        results = state.get("raw_results", [])

        # Format results for the prompt
        if not results:
            results_str = "No results found."
        elif len(results) > 20:
            # Truncate for large result sets
            results_str = json.dumps(results[:20], indent=2, default=str)
            results_str += f"\n... and {len(results) - 20} more results"
        else:
            results_str = json.dumps(results, indent=2, default=str)

        prompt = RESULT_INTERPRETATION_PROMPT.format(
            query=state["query"],
            cypher=state.get("cypher_query", ""),
            results=results_str,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response).strip()

        return {
            "interpreted_response": response_text,
            "result": QueryResult(
                success=True,
                data=results,
                interpretation=response_text,
                cypher_used=state.get("cypher_query", ""),
            ),
        }

    def _refine_query(self, state: GraphRAGState) -> dict:
        """Refine a failed Cypher query."""
        prompt = QUERY_REFINEMENT_PROMPT.format(
            query=state["query"],
            cypher=state.get("cypher_query", ""),
            error=state.get("error", "Unknown error"),
            schema=SCHEMA_DESCRIPTION,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            return {
                "cypher_query": result.get("cypher", ""),
                "query_explanation": result.get("explanation", ""),
                "return_type": result.get("return_type", "list"),
                "retry_count": state.get("retry_count", 0) + 1,
                "error": None,
            }
        except json.JSONDecodeError:
            return {
                "error": f"Failed to refine query: {response_text[:200]}",
                "retry_count": state.get("retry_count", 0) + 1,
            }

    def _should_refine(self, state: GraphRAGState) -> str:
        """Decide whether to refine the query or interpret results."""
        error = state.get("error")
        retry_count = state.get("retry_count", 0)

        # Refine if there's an error and we haven't exceeded retry limit
        if error and retry_count < 2:
            return "refine"
        return "interpret"

    def query(self, query: str, context: str = None) -> QueryResult:
        """Execute a natural language query against the listening history.

        Args:
            query: Natural language question about listening history
            context: Optional context from previous steps

        Returns:
            QueryResult with data and interpretation
        """
        initial_state: GraphRAGState = {
            "query": query,
            "context": context,
            "cypher_query": "",
            "query_explanation": "",
            "return_type": "",
            "raw_results": [],
            "interpreted_response": "",
            "error": None,
            "retry_count": 0,
            "result": None,
        }

        final_state = self.graph.invoke(initial_state)

        # Return the result or construct an error result
        if final_state.get("result"):
            return final_state["result"]

        return QueryResult(
            success=False,
            data=[],
            interpretation=final_state.get("error") or "Query failed",
            cypher_used=final_state.get("cypher_query", ""),
        )


def create_graph_rag_agent(llm=None, neo4j_config: dict = None) -> GraphRAGAgent:
    """Factory function to create a GraphRAGAgent.

    Args:
        llm: Optional LLM instance (defaults to Gemini)
        neo4j_config: Optional Neo4j config dict

    Returns:
        Configured GraphRAGAgent
    """
    return GraphRAGAgent(llm=llm, neo4j_config=neo4j_config)
