"""Router Agent - Single LLM call for query analysis and routing."""

import json
import re
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import RouterState, ExecutionStep
from ..prompts.router_prompts import UNIFIED_ROUTER_PROMPT
from ..utils.config import get_gemini_llm

# TODO add logging to capture response_text incase parsing fails
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


class RouterAgent:
    """Router class for user queries using a single LLM call.

    Routes queries to either:
    - graph_rag: Historical analysis via Neo4j
    - spotify: Live Spotify operations

    Handles multi-part queries by decomposing and routing in one step.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_gemini_llm()

    def route(self, query: str) -> RouterState:
        """Route a user query with a single LLM call.

        Args:
            query: Raw user input

        Returns:
            RouterState with a populated execution_plan list
        """
        prompt = UNIFIED_ROUTER_PROMPT.format(query=query)
        response = self.llm.invoke([HumanMessage(content=prompt)])
        response_text = get_response_text(response)

        try:
            result = parse_json_response(response_text)

            cleaned_query = result.get("cleaned_query", query)
            raw_plan = result.get("execution_plan", [])

            # Convert to ExecutionStep objects
            execution_plan = []
            for step_data in raw_plan:
                execution_plan.append(
                    ExecutionStep(
                        step=step_data.get("step", len(execution_plan)),
                        query=step_data.get("query", ""),
                        route=step_data.get("route", "graph_rag"),
                        depends_on=step_data.get("depends_on"),
                        context_needed=step_data.get("context_needed"),
                    )
                )

            # Handle empty plan - create single step
            if not execution_plan:
                execution_plan = [
                    ExecutionStep(
                        step=0,
                        query=cleaned_query,
                        route="graph_rag",
                        depends_on=None,
                        context_needed=None,
                    )
                ]

        except json.JSONDecodeError:
            # Fallback: single graph_rag step with original query
            cleaned_query = query
            execution_plan = [
                ExecutionStep(
                    step=0,
                    query=query,
                    route="graph_rag",
                    depends_on=None,
                    context_needed=None,
                )
            ]

        return RouterState(
            original_query=query,
            cleaned_query=cleaned_query,
            is_multi_part=len(execution_plan) > 1,
            execution_plan=execution_plan,
            current_step=0,
            intermediate_results={},
            final_response=None,
        )

