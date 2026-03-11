"""Graph RAG Worker Agent for LangGraph."""

import json
from langchain_core.tools import tool
from langchain.agents import create_agent

# Import prompts and configs
from ..prompts.graph_rag_prompts import GRAPH_WORKER_SYSTEM_PROMPT
from ..utils.config import get_gemini_llm

def get_neo4j_db():
    from neo4j_db import Neo4jDatabase
    from ..utils.config import get_neo4j_config
    config = get_neo4j_config()
    db = Neo4jDatabase(uri=config["uri"], auth=(config["user"], config["password"]))
    db.connect()
    return db

@tool
def generate_and_execute_cypher(cypher_query: str) -> str:
    """Execute a read-only Cypher query against the Neo4j database to find user listening history.
    
    Args:
        cypher_query: The exact Cypher string to execute. Example: 'MATCH (u:User)-[:PERFORMED]->(e:ListenEvent) RETURN count(e)'
    """
    db = get_neo4j_db()
    try:
        # Prevent any write operations for safety
        upper_query = cypher_query.upper()
        if any(keyword in upper_query for keyword in ["CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"]):
            return "Error: This tool only supports read-only MATCH queries."
            
        results = db._execute_query(cypher_query)
        db.close()
        
        # Limit the output size to prevent context overflow in the LLM
        if len(results) > 50:
            results = results[:50]
            return json.dumps({"data": results, "note": "Results truncated to top 50 items."})
            
        return json.dumps({"data": results})
        
    except Exception as e:
        if db:
            db.close()
        return f"Database Error: {str(e)}. Please analyze this error and fix the cypher query."

# Compile the Graph RAG Worker Graph
graph_tools = [generate_and_execute_cypher]

def build_graph_worker():
    """Builds and returns the Graph RAG ReAct agent."""
    # Using Gemini Pro/Flash for better coding (Cypher) capabilities
    llm = get_gemini_llm(temperature=0)
    agent = create_agent(
        llm,
        tools=graph_tools,
        system_prompt=GRAPH_WORKER_SYSTEM_PROMPT
    )
    return agent