"""Response Synthesis Agent - Combines results into coherent responses."""

import json
from typing import List
from langchain_core.messages import HumanMessage

from ..schemas.state_schemas import SynthesisState, StepResult, QueryResult
from ..prompts.synthesis_prompts import (
    RESPONSE_SYNTHESIS_PROMPT,
    MULTI_RESULT_SYNTHESIS_PROMPT,
    CHAINED_RESULT_SYNTHESIS_PROMPT,
    ERROR_SYNTHESIS_PROMPT,
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


class SynthesisAgent:
    """Agent for combining execution results into coherent user responses.

    Uses Gemini to synthesize results from Graph RAG and Spotify agent queries
    into natural language responses.
    """

    def __init__(self, llm=None):
        """Initialize the Synthesis Agent.

        Args:
            llm: Optional LLM instance (defaults to Gemini)
        """
        self.llm = llm or get_gemini_llm()

    def synthesize(
        self,
        original_query: str,
        step_results: List[StepResult],
    ) -> str:
        """Synthesize execution results into a final response.

        Args:
            original_query: The user's original question/request
            step_results: Results from each execution step

        Returns:
            Natural language response
        """
        # Determine synthesis type
        synthesis_type = self._determine_synthesis_type(step_results)

        # Build state
        state: SynthesisState = {
            "original_query": original_query,
            "step_results": step_results,
            "synthesis_type": synthesis_type,
            "has_errors": any(not r["result"]["success"] for r in step_results),
            "final_response": "",
        }

        # Generate response based on type
        if synthesis_type == "error":
            return self._synthesize_error(state)
        elif synthesis_type == "single":
            return self._synthesize_single(state)
        elif synthesis_type == "chained":
            return self._synthesize_chained(state)
        else:  # multi
            return self._synthesize_multi(state)

    def _determine_synthesis_type(self, step_results: List[StepResult]) -> str:
        """Determine which synthesis approach to use."""
        if not step_results:
            return "error"

        # Check if all failed
        all_failed = all(not r["result"]["success"] for r in step_results)
        if all_failed:
            return "error"

        # Single result
        if len(step_results) == 1:
            return "single"

        # Check for chained (one depends on another)
        has_dependency = any(r.get("context_used") for r in step_results)
        if has_dependency and len(step_results) == 2:
            return "chained"

        # Multiple independent results
        return "multi"

    def _synthesize_single(self, state: SynthesisState) -> str:
        """Synthesize a single result."""
        result = state["step_results"][0]

        prompt = RESPONSE_SYNTHESIS_PROMPT.format(
            original_query=state["original_query"],
            execution_results=self._format_single_result(result),
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return get_response_text(response).strip()

    def _synthesize_multi(self, state: SynthesisState) -> str:
        """Synthesize multiple independent results."""
        # Use _format_single_result to include actual data, not just interpretation
        sub_query_results = "\n\n".join(
            f"### Query {i+1}\n{self._format_single_result(r)}"
            for i, r in enumerate(state["step_results"])
        )

        prompt = MULTI_RESULT_SYNTHESIS_PROMPT.format(
            original_query=state["original_query"],
            sub_query_results=sub_query_results,
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return get_response_text(response).strip()

    def _synthesize_chained(self, state: SynthesisState) -> str:
        """Synthesize chained results (data lookup → action)."""
        results = state["step_results"]

        # Find the data step (usually graph_rag) and action step (usually spotify)
        data_result = None
        action_result = None

        for r in results:
            if r["route"] == "graph_rag":
                data_result = r
            elif r["route"] == "spotify":
                action_result = r

        # Fallback if routes don't match expected pattern
        if not data_result or not action_result:
            data_result = results[0]
            action_result = results[-1]

        prompt = CHAINED_RESULT_SYNTHESIS_PROMPT.format(
            original_query=state["original_query"],
            data_result=self._format_single_result(data_result),
            action_result=self._format_single_result(action_result),
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return get_response_text(response).strip()

    def _synthesize_error(self, state: SynthesisState) -> str:
        """Synthesize error response."""
        results = state["step_results"]

        error_details = []
        partial_results = []

        for r in results:
            if r["result"]["success"]:
                partial_results.append(self._format_single_result(r))
            else:
                error_details.append(
                    f"Query: {r['query']}\nError: {r['result']['interpretation']}"
                )

        prompt = ERROR_SYNTHESIS_PROMPT.format(
            original_query=state["original_query"],
            error_details="\n\n".join(error_details) if error_details else "No specific errors recorded",
            partial_results="\n\n".join(partial_results) if partial_results else "None",
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return get_response_text(response).strip()

    def _format_single_result(self, result: StepResult) -> str:
        """Format a single step result for the prompt."""
        data = result['result'].get('data', [])
        route = result['route']

        # Format data based on route type
        if route == "graph_rag":
            # Neo4j returns list of dicts
            if data:
                data_str = json.dumps(data[:10], indent=2, default=str)
                if len(data) > 10:
                    data_str += f"\n... and {len(data) - 10} more results"
            else:
                data_str = "No data returned"
        elif route == "spotify":
            # Spotify agent returns list of tool results with 'result' strings
            if data:
                data_str = "\n".join([
                    f"Tool: {d.get('tool', 'unknown')}\nOutput: {d.get('result', 'N/A')}"
                    for d in data
                ])
            else:
                data_str = "No tool results"
        else:
            data_str = str(data)

        return (
            f"Query: {result['query']}\n"
            f"Route: {route}\n"
            f"Success: {result['result']['success']}\n"
            f"Data:\n{data_str}"
        )


def create_synthesis_agent(llm=None) -> SynthesisAgent:
    """Factory function to create a SynthesisAgent.

    Args:
        llm: Optional LLM instance (defaults to Gemini)

    Returns:
        Configured SynthesisAgent
    """
    return SynthesisAgent(llm=llm)
