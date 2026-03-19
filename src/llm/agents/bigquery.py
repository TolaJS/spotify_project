"""BigQuery Worker Agent for LangGraph."""

import json
import logging
import os
import sys

from langchain_core.tools import tool
from langchain.agents import create_agent

from ..prompts.bigquery_prompts import BIGQUERY_WORKER_SYSTEM_PROMPT
from ..utils.config import get_gemini_llm
from auth.oauth_handler import current_user_id as spotify_user_ctx

logger = logging.getLogger(__name__)

_WRITE_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "MERGE", "TRUNCATE"}


def _get_bigquery_db():
    _ingestion_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../ingestion")
    )
    if _ingestion_dir not in sys.path:
        sys.path.insert(0, _ingestion_dir)
    from bigquery_db import BigQueryDatabase

    project_id = os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2")
    dataset_id = os.getenv("BQ_DATASET_ID", "timber")
    db = BigQueryDatabase(project_id=project_id, dataset_id=dataset_id)
    db.connect()
    return db


@tool
def execute_sql(sql_query: str) -> str:
    """Execute a read-only BigQuery SQL query to answer questions about the user's Spotify listening history.

    Args:
        sql_query: A standard SQL SELECT statement against the `timber` dataset.
                   Example: 'SELECT COUNT(*) AS total FROM `timber.listening_events` WHERE user_id = \"abc123\" AND ts >= TIMESTAMP(\\'2008-01-01\\')'
    """
    db = _get_bigquery_db()
    try:
        upper = sql_query.upper().strip()
        if any(kw in upper for kw in _WRITE_KEYWORDS):
            return "Error: Only SELECT queries are allowed."

        user_id = spotify_user_ctx.get()
        if user_id and not db.user_has_data(user_id):
            db.close()
            return (
                "No listening history found for this user. They have not uploaded any Spotify Extended "
                "Streaming History data yet. Let the user know they can upload their data using the "
                "Upload History button in the sidebar."
            )

        results = db.execute_query(sql_query)
        db.close()

        if not results:
            return json.dumps({
                "data": [],
                "note": (
                    "Query executed successfully but returned no results. "
                    "The requested data does not exist in the user's listening history. "
                    "Do not retry. Return this finding to the caller immediately."
                ),
            })

        if len(results) > 50:
            results = results[:50]
            return json.dumps(
                {"data": results, "note": "Results truncated to top 50 items."},
                default=str,
            )

        return json.dumps({"data": results}, default=str)

    except Exception as e:
        if db:
            db.close()
        return (
            f"Database Error: {str(e)}. "
            "Analyze the error: if it is a syntax or schema issue (wrong table name, column name, "
            "missing JOIN condition, etc.), fix the SQL and retry. "
            "If the error suggests the data simply does not exist, do not retry — inform the user instead."
        )


# BigQuery Worker tools
bigquery_tools = [execute_sql]


def build_bigquery_worker():
    """Builds and returns the BigQuery ReAct agent."""
    llm = get_gemini_llm(temperature=0)
    agent = create_agent(
        llm,
        tools=bigquery_tools,
        system_prompt=BIGQUERY_WORKER_SYSTEM_PROMPT,
    )
    return agent
