"""Orchestrator - Coordinates all agents to process user queries.

Steps are submitted to a thread pool and each step blocks only on its
specific dependency's Future, not on an entire batch.
"""

import json
import threading
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, Future

from .schemas.state_schemas import (
    ExecutionStep,
    StepResult,
    QueryResult,
)
from .agents.router import RouterAgent
from .agents.graph_rag import GraphRAGAgent
from .agents.spotify import SpotifyAgent
from .agents.synthesis import SynthesisAgent


class Orchestrator:
    """Coordinates Router, Graph RAG, Spotify, and Synthesis agents."""

    def __init__(
        self,
        router: RouterAgent = None,
        graph_rag: GraphRAGAgent = None,
        spotify: SpotifyAgent = None,
        synthesis: SynthesisAgent = None,
    ):
        self.router = router or RouterAgent()
        self.graph_rag = graph_rag or GraphRAGAgent()
        self.spotify = spotify or SpotifyAgent()
        self.synthesis = synthesis or SynthesisAgent()

    def _execute_single_step(
        self,
        step: ExecutionStep,
        completed_results: Dict[int, StepResult],
    ) -> StepResult:
        """Execute a single step, passing context from dependencies if any."""
        context = self._get_context_for_step(step, completed_results)

        if step["route"] == "graph_rag":
            result = self.graph_rag.query(step["query"], context=context)
        else:
            result = self.spotify.query(step["query"], context=context)

        return StepResult(
            step=step["step"],
            query=step["query"],
            route=step["route"],
            result=result,
            context_used=context,
        )

    def _get_context_for_step(
        self,
        step: ExecutionStep,
        completed_results: Dict[int, StepResult],
    ) -> Optional[str]:
        """Build a context string from the dependency step's results."""
        depends_on = step.get("depends_on")
        if depends_on is None:
            return None

        if depends_on in completed_results:
            result = completed_results[depends_on]
            interpretation = result["result"]["interpretation"]
            data = result["result"].get("data", [])

            context_parts = [f"Previous result: {interpretation}"]

            if data:
                if isinstance(data, list) and len(data) > 0:
                    items_to_include = data[:10]
                    context_parts.append(f"Data ({len(data)} total items):")
                    context_parts.append(json.dumps(items_to_include, indent=2, default=str))

            return "\n".join(context_parts)

        return None

    def _execute_plan_parallel(
        self, execution_plan: List[ExecutionStep]
    ) -> List[StepResult]:
        """Execute all steps with per-dependency parallelism using Futures."""
        step_futures: Dict[int, Future] = {}
        completed_results: Dict[int, StepResult] = {}
        lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=len(execution_plan)) as executor:
            # Submit all steps immediately. Dependent steps will block in their
            # own threads until their specific dependency completes.
            for step in execution_plan:
                dep_idx = step.get("depends_on")
                dep_future = step_futures.get(dep_idx) if dep_idx is not None else None

                def run_step(s=step, df=dep_future):  # default args capture loop values
                    # Wait for dependency to finish (if any)
                    if df is not None:
                        df.result()

                    # Snapshot results under lock for thread-safe read
                    with lock:
                        results_snapshot = dict(completed_results)

                    # Run the agent (graph_rag or spotify)
                    result = self._execute_single_step(s, results_snapshot)

                    # Store result for downstream steps
                    with lock:
                        completed_results[s["step"]] = result

                    return result

                step_futures[step["step"]] = executor.submit(run_step)

            # Collect results, replacing failures with error StepResults
            all_results = []
            for step in execution_plan:
                try:
                    result = step_futures[step["step"]].result()
                    all_results.append(result)
                except Exception as e:
                    all_results.append(
                        StepResult(
                            step=step["step"],
                            query=step["query"],
                            route=step["route"],
                            result=QueryResult(
                                success=False,
                                data=[],
                                interpretation=f"Error: {str(e)}",
                                cypher_used=None,
                            ),
                            context_used=None,
                        )
                    )

        all_results.sort(key=lambda r: r["step"])
        return all_results

    def query(self, query: str) -> dict:
        """Process a user query through the full pipeline.

        Returns dict with 'response', 'success', and 'details'.
        """
        # 1. Route: analyze query and build execution plan
        router_result = self.router.route(query)
        execution_plan = router_result["execution_plan"]

        if not execution_plan:
            return {
                "response": "I couldn't understand your query. Please try again.",
                "success": False,
                "details": {"execution_plan": [], "step_results": []},
            }

        # 2. Execute: run all steps in parallel (respecting dependencies)
        all_results = self._execute_plan_parallel(execution_plan)

        # 3. Synthesize: combine results into a final response
        final_response = self.synthesis.synthesize(
            original_query=query,
            step_results=all_results,
        )

        success = all(r["result"]["success"] for r in all_results)

        return {
            "response": final_response,
            "success": success,
            "details": {
                "execution_plan": execution_plan,
                "step_results": all_results,
            },
        }

    def close(self):
        """Close connections for all agents."""
        if hasattr(self.graph_rag, "close"):
            self.graph_rag.close()
