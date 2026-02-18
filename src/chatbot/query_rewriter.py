"""Query Rewriter - Resolves conversational references into self-contained queries."""

from typing import List
from langchain_core.messages import HumanMessage

from llm.utils.config import get_gemini_llm
from chatbot.schemas import Turn
from chatbot.prompts import QUERY_REWRITE_PROMPT


def get_response_text(response) -> str:
    """Extract text content from LLM response, handling different formats."""
    content = response.content
    if isinstance(content, list):
        return "".join(
            part.get("text", str(part)) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


class QueryRewriter:
    """Rewrites follow-up queries to be self-contained.

    Takes recent conversation history and the current query,
    produces a query with all references resolved.
    """

    MAX_HISTORY_TURNS = 10

    def __init__(self, llm=None):
        self.llm = llm or get_gemini_llm()

    def rewrite(self, query: str, history: List[Turn]) -> str:
        """Rewrite a query using conversation history.

        Args:
            query: The user's latest message
            history: List of previous Turn dicts

        Returns:
            Self-contained query string
        """
        recent = history[-self.MAX_HISTORY_TURNS:]
        history_str = self._format_history(recent)

        prompt = QUERY_REWRITE_PROMPT.format(
            history=history_str,
            query=query,
        )

        response = self.llm.invoke([HumanMessage(content=prompt)])
        rewritten = get_response_text(response).strip()

        # Guard: if LLM returns empty, fall back to original
        return rewritten if rewritten else query

    def _format_history(self, turns: List[Turn]) -> str:
        """Format turns into a readable history string.

        Uses the rewritten query (if available) instead of the raw user input
        so the LLM sees resolved references, avoiding chain-of-reference issues.
        """
        lines = []
        for turn in turns:
            q = turn.get("rewritten_query") or turn["query"]
            lines.append(f"  User: {q}")
            lines.append(f"  Assistant: {turn['response']}")
        return "\n".join(lines)
