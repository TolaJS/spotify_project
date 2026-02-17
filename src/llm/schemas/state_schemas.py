from typing import TypedDict, List, Literal, Optional, Any

RouteType = Literal["graph_rag", "spotify"]


class SubQuery(TypedDict):
    """A decomposed sub-query with routing information."""
    original_text: str
    cleaned_text: str
    route: Optional[RouteType]
    depends_on: Optional[int]  # Index of sub-query this depends on
    context_needed: Optional[str]  # What context is needed from dependency


class ExecutionStep(TypedDict):
    """A single step in the execution plan."""
    step: int
    query: str
    route: RouteType
    depends_on: Optional[int]
    context_needed: Optional[str]


class RouterState(TypedDict):
    """Main state for the router agent."""
    # Input
    original_query: str

    # Processing
    cleaned_query: str
    is_multi_part: bool
    sub_queries: List[SubQuery]

    # Execution
    execution_plan: List[ExecutionStep]
    current_step: int
    intermediate_results: dict[int, Any]

    # Output
    final_response: Optional[str]


class QueryResult(TypedDict):
    """Result from a Graph RAG or Spotify agent query."""
    success: bool
    data: List[Any]
    interpretation: str
    cypher_used: Optional[str]  # Only for Graph RAG


class GraphRAGState(TypedDict):
    """State for the Graph RAG agent."""
    # Input
    query: str
    context: Optional[str]  # Context from previous steps

    # Cypher generation
    cypher_query: str
    query_explanation: str
    return_type: str  # "single_value", "list", "table", "aggregation"

    # Execution
    raw_results: List[Any]
    interpreted_response: str

    # Error handling
    error: Optional[str]
    retry_count: int

    # Output
    result: Optional[QueryResult]


class ToolCall(TypedDict):
    """A single tool call with arguments."""
    name: str
    arguments: dict
    reason: Optional[str]


class SpotifyAgentState(TypedDict):
    """State for the Spotify agent."""
    # Input
    query: str
    context: Optional[str]  # Context from previous steps (e.g., track info from Graph RAG)

    # Tool selection
    selected_tools: List[ToolCall]
    current_tool_index: int
    requires_search_first: bool

    # Execution
    tool_results: List[dict]  # Results from each tool execution
    interpreted_response: str

    # Error handling
    error: Optional[str]
    retry_count: int

    # Output
    result: Optional[QueryResult]


class StepResult(TypedDict):
    """Result from a single execution step."""
    step: int
    query: str
    route: RouteType
    result: QueryResult
    context_used: Optional[str]


SynthesisType = Literal["single", "multi", "chained", "error"]


class SynthesisState(TypedDict):
    """State for the Response Synthesis agent."""
    # Input
    original_query: str
    step_results: List[StepResult]

    # Processing
    synthesis_type: SynthesisType  # Determines which prompt to use
    has_errors: bool

    # Output
    final_response: str


class OrchestratorState(TypedDict):
    """State for the main Orchestrator."""
    # Input
    original_query: str

    # Router output
    execution_plan: List[ExecutionStep]

    # Execution tracking
    current_step: int
    step_results: List[StepResult]

    # Final output
    final_response: str
    success: bool
