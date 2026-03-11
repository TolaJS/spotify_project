import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class HistoryRepository:
    """Manages chat history persistence in Neo4j.
    
    This is purely for saving/loading state for the frontend UI and ConversationManager memory.
    This data is NOT indexed for Graph RAG searches and is entirely hidden from the AI agents.
    """

    def __init__(self, neo4j_db):
        """
        Args:
            neo4j_db: An instance of the Neo4jDatabase class.
        """
        self.db = neo4j_db

    def save_session(self, user_id: str, session: dict) -> bool:
        """Saves an entire session and all its turns to Neo4j.
        Overwrites any existing turns for this session to ensure consistency.
        """
        if not self.db._driver:
            logger.error("Cannot save history: No Neo4j connection.")
            return False

        try:
            # 1. Ensure User node exists and Session node exists, then delete old turns
            query = """
            MERGE (u:User {id: $user_id})
            MERGE (s:ChatSession {id: $session_id})
            MERGE (u)-[:HAS_SESSION]->(s)
            SET s.last_active = $last_active, s.created_at = $created_at
            
            // Delete existing turns for this session to replace them cleanly
            WITH s
            OPTIONAL MATCH (s)-[r:HAS_TURN]->(t:ChatTurn)
            DELETE r, t
            """
            
            self.db._execute_query(query, {
                "user_id": user_id,
                "session_id": session["session_id"],
                "last_active": session["last_active"],
                "created_at": session["created_at"]
            })

            # 2. Insert all turns sequentially
            for i, turn in enumerate(session["turns"]):
                turn_query = """
                MATCH (s:ChatSession {id: $session_id})
                CREATE (t:ChatTurn {
                    turn_index: $turn_index,
                    query: $query,
                    rewritten_query: $rewritten_query,
                    response: $response,
                    success: $success,
                    timestamp: $timestamp,
                    step_results: $step_results
                })
                CREATE (s)-[:HAS_TURN]->(t)
                """
                
                # We serialize step_results to JSON so it fits in a Neo4j string property
                step_results_json = json.dumps(turn.get("step_results") or [])
                
                self.db._execute_query(turn_query, {
                    "session_id": session["session_id"],
                    "turn_index": i,
                    "query": turn["query"],
                    "rewritten_query": turn.get("rewritten_query"),
                    "response": turn["response"],
                    "success": turn["success"],
                    "timestamp": turn["timestamp"],
                    "step_results": step_results_json
                })
            
            logger.info(f"Saved session {session['session_id']} to Neo4j for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save session to Neo4j: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[dict]:
        """Loads a full session and its turns from Neo4j."""
        if not self.db._driver:
            return None

        try:
            # 1. Get the session metadata
            session_query = "MATCH (s:ChatSession {id: $session_id}) RETURN s.created_at as created_at, s.last_active as last_active"
            session_result = self.db._execute_query(session_query, {"session_id": session_id})
            
            if not session_result:
                return None
                
            session_data = session_result[0]
            
            # 2. Get all turns ordered by index
            turns_query = """
            MATCH (s:ChatSession {id: $session_id})-[:HAS_TURN]->(t:ChatTurn)
            RETURN t.query as query, 
                   t.rewritten_query as rewritten_query, 
                   t.response as response, 
                   t.success as success, 
                   t.timestamp as timestamp, 
                   t.step_results as step_results
            ORDER BY t.turn_index ASC
            """
            turns_result = self.db._execute_query(turns_query, {"session_id": session_id})
            
            # Reconstruct the turns list
            turns = []
            for t in turns_result:
                turns.append({
                    "query": t["query"],
                    "rewritten_query": t["rewritten_query"],
                    "response": t["response"],
                    "success": t["success"],
                    "timestamp": t["timestamp"],
                    "step_results": json.loads(t["step_results"]) if t["step_results"] else None
                })
                
            return {
                "session_id": session_id,
                "created_at": session_data["created_at"],
                "last_active": session_data["last_active"],
                "turns": turns
            }

        except Exception as e:
            logger.error(f"Failed to load session from Neo4j: {e}")
            return None

    def get_latest_session_id(self, user_id: str, exclude_session_id: str = None) -> Optional[str]:
        """Gets the most recently active session ID for a user.
        Useful for the 'Previous Chat' button.
        """
        if not self.db._driver:
            return None

        try:
            query = """
            MATCH (u:User {id: $user_id})-[:HAS_SESSION]->(s:ChatSession)
            WHERE s.id <> $exclude_id
            RETURN s.id as session_id
            ORDER BY s.last_active DESC
            LIMIT 1
            """
            
            result = self.db._execute_query(query, {
                "user_id": user_id, 
                "exclude_id": exclude_session_id or ""
            })
            
            if result and len(result) > 0:
                return result[0]["session_id"]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get latest session for user {user_id}: {e}")
            return None