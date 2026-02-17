"""Graph RAG Agent - Queries Neo4j for historical Spotify listening data."""

import json
import re
from neo4j import GraphDatabase
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import QueryResult
from ..prompts.graph_rag_prompts import (
    SCHEMA_DESCRIPTION,
    CYPHER_GENERATION_PROMPT,
    QUERY_REFINEMENT_PROMPT,
)
from ..utils.config import get_gemini_llm, get_neo4j_config


def get_response_text(response) -> str:
    """Extract text content from LLM response."""
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


class GraphRAGAgent:
    """Agent for querying Spotify listening history via Neo4j.

    General Flow:
    1. Generate Cypher query from natural language
    2. Execute against Neo4j
    3. Retry up to 2 times if query fails
    4. Return raw results (Synthesis agent handles interpretation)
    """

    def __init__(self, llm=None, neo4j_config: dict = None):
        self.llm = llm or get_gemini_llm()
        self.neo4j_config = neo4j_config or get_neo4j_config()
        self._driver = None

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

    def _generate_cypher(self, query: str, context: str = None) -> tuple[str, str]:
        """Generate Cypher query from natural language.

        Returns:
            Tuple of (cypher_query, error_message)
        """
        prompt = CYPHER_GENERATION_PROMPT.format(
            schema=SCHEMA_DESCRIPTION,
            query=query,
            context=context or "None",
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            return result.get("cypher", ""), None
        except json.JSONDecodeError:
            return "", f"Failed to parse response: {response_text[:200]}"

    def _execute_cypher(self, cypher: str) -> tuple[list, str]:
        """Execute Cypher query against Neo4j.

        Returns:
            Tuple of (results, error_message)
        """
        if not cypher:
            return [], "No Cypher query provided"

        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run(cypher)
                records = [record.data() for record in result]
            return records, None
        except Exception as e:
            return [], str(e)

    def _refine_cypher(self, query: str, cypher: str, error: str) -> tuple[str, str]:
        """Refine a failed Cypher query.

        Returns:
            Tuple of (refined_cypher, error_message)
        """
        prompt = QUERY_REFINEMENT_PROMPT.format(
            query=query,
            cypher=cypher,
            error=error,
            schema=SCHEMA_DESCRIPTION,
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)
            return result.get("cypher", ""), None
        except json.JSONDecodeError:
            return "", f"Failed to refine query: {response_text[:200]}"

    def query(self, query: str, context: str = None) -> QueryResult:
        """Execute a natural language query against the listening history.

        Args:
            query: Natural language question about listening history.
            context: Optional string containing results from previous execution steps
                     (e.g., "Artist: Taylor Swift") to resolve ambiguities like "by them".

        Returns:
            QueryResult with raw data (interpretation done by Synthesis agent)
        """
        # Step 1: Generate Cypher
        cypher, error = self._generate_cypher(query, context)

        if error:
            return QueryResult(
                success=False,
                data=[],
                interpretation=error,
                cypher_used="",
            )

        # Step 2: Execute with retry loop
        max_retries = 2
        results = []

        for attempt in range(max_retries + 1):
            results, error = self._execute_cypher(cypher)

            if error is None:
                break

            if attempt < max_retries:
                # Try to refine the query
                cypher, refine_error = self._refine_cypher(query, cypher, error)
                if refine_error:
                    error = refine_error
                    break

        # Step 3: Return results
        if error:
            return QueryResult(
                success=False,
                data=[],
                interpretation=f"Query error: {error}",
                cypher_used=cypher,
            )

        interpretation = "No results found." if not results else f"Found {len(results)} result(s)."

        return QueryResult(
            success=True,
            data=results,
            interpretation=interpretation,
            cypher_used=cypher,
        )
