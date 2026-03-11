"""Interactive test script for the LLM2 manager agent.

Run from the project root:
    python -m src.llm_2.test_chat

Or for a single prompt:
    python -m src.llm_2.test_chat "Play Bohemian Rhapsody by Queen"
"""

import sys
from pathlib import Path

# Allow running directly: python src/llm_2/test_chat.py
_project_root = Path(__file__).resolve().parents[2]
_src_root = _project_root / "src"
for _p in [str(_project_root), str(_src_root), str(_src_root / "graph-rag")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load .env from project root
load_dotenv(_project_root / ".env")

# Sample prompts covering different agent paths
SAMPLE_PROMPTS = [
    # Spotify agent
    "Play Yellow by Coldplay",
    "Queue Blinding Lights by The Weeknd",
    "What's currently playing?",'who produced it',
    # Graph RAG agent
    "What are my top 5 most played tracks?",
    "Who is my most listened to artist?",
    # Google Search (via manager grounding)
    "Who won the Grammy for Album of the Year in 2024?",
    # Out-of-scope (should be declined)
    "What's the best recipe for pasta?",
    # Multi-step
    "Find my most played song and play it",
]


def _extract_text(content) -> str:
    """Extract plain text from a string or a list of content blocks."""
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content or ""


def run(prompt: str, mgr, session_id: str) -> tuple[str, list]:
    """Invoke the orchestrator with the prompt and print tool calls from the raw state."""
    # We call the orchestrator's chat method directly, exactly as websocket.py does
    response = mgr.chat(prompt, session_id=session_id)
    
    # We can dig into the raw LangGraph state to print tool usage for debugging
    session = mgr.get_session(response["session_id"])
    if session and session["turns"]:
        last_turn = session["turns"][-1]
        step_results = last_turn.get("step_results", [])
        for step in step_results:
            tool_name = step.get("tool", "unknown_tool")
            print(f"  [tool] {tool_name}() -> executed successfully")
            
    return response["response"], response["session_id"]


def main():
    print("Building LangGraph Orchestrator...")
    from src.llm.langgraph_orchestrator import LangGraphOrchestrator
    mgr = LangGraphOrchestrator()
    print("Agent ready.\n")

    session_id = "test_cli_user"

    # Single prompt mode (passed as CLI arg)
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"User: {prompt}")
        response, _ = run(prompt, mgr, session_id)
        print(f"Timbre: {response}\n")
        return

    # Interactive mode
    print("Entering interactive mode. Type 'quit' to exit, 'reset' to clear history, or 'samples' to run all sample prompts.\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("Goodbye.")
            break
        if user_input.lower() == "reset":
            mgr.close_session(session_id)
            print("  [history cleared]\n")
            continue
        if user_input.lower() == "samples":
            mgr.close_session(session_id)
            for prompt in SAMPLE_PROMPTS:
                print(f"\nUser: {prompt}")
                response, session_id = run(prompt, mgr, session_id)
                print(f"Timbre: {response}")
            print()
            continue

        response, session_id = run(user_input, mgr, session_id)
        print(f"Timbre: {response}\n")


if __name__ == "__main__":
    main()
