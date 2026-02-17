"""Prompts for the Graph RAG agent - Cypher query generation."""

SCHEMA_DESCRIPTION = """
## Neo4j Graph Schema

### Nodes

**User**
- id (unique), name, url (use 'kanljakm68dmhxs19itsmgbku' as the default userid in queries)

**Track**
- id (unique - ISRC or Spotify ID), name, url, duration_ms, isrc, spotify_id

**Artist**
- id (unique), name, url

**Album**
- id (unique - UPC or Spotify ID), name, type, url, release_date, total_tracks, upc, spotify_id

**Genre**
- name (unique)

**ListenEvent**
- id (unique), timestamp (datetime), ms_played, skipped (boolean), incognito (boolean), is_valid_listen (boolean - 10s+), is_full_listen (boolean - 30s+)

**Time Tree:**
- Year: year (int)
- Month: month (int), year (int), name (string)
- Day: date (date), day (int)
- Hour: hour (int, 0-23)
- DayOfWeek: day (int, 1=Monday to 7=Sunday), name (string)

### Relationships

**Listening:**
- (User)-[:PERFORMED]->(ListenEvent)
- (ListenEvent)-[:IS_LISTEN_OF]->(Track)

**Music Metadata:**
- (Track)-[:PERFORMED_BY]->(Artist)
- (Track)-[:BELONGS_TO_ALBUM]->(Album)
- (Artist)-[:HAS_GENRE]->(Genre)
- (Artist)-[:HAS_ALBUM]->(Album)
- (Artist)-[:COLLABORATED_WITH {count: int}]->(Artist)

**Time Tree:**
- (ListenEvent)-[:OCCURRED_ON]->(Day)
- (ListenEvent)-[:OCCURRED_AT_HOUR]->(Hour)
- (Year)-[:HAS_MONTH]->(Month)
- (Month)-[:HAS_DAY]->(Day)
- (Day)-[:IS_DAY_OF_WEEK]->(DayOfWeek)
"""

CYPHER_GENERATION_PROMPT = """You are a Cypher query expert for a Spotify listening history database.

{schema}

## Query Guidelines

1. **Time Filtering:**
   - Use the time tree for date-based queries
   - Example: `MATCH (le:ListenEvent)-[:OCCURRED_ON]->(d:Day)-[:HAS_DAY]-(m:Month)-[:HAS_MONTH]-(y:Year {{year: 2023}})`
   - For specific months: `MATCH (m:Month {{year: 2023, month: 6}})-[:HAS_DAY]->(d:Day)<-[:OCCURRED_ON]-(le:ListenEvent)`

2. **Counting Listens:**
   - Use `is_valid_listen = true` for meaningful listens (10s+)
   - Use `is_full_listen = true` for complete listens (30s+)
   - Count events: `COUNT(le)` or `COUNT(DISTINCT le)`

3. **Top Artists/Tracks:**
   - Group by artist/track and order by count
   - Example: `WITH a, COUNT(le) as listens ORDER BY listens DESC LIMIT 10`

4. **Time of Day Analysis:**
   - Use Hour nodes: `MATCH (le)-[:OCCURRED_AT_HOUR]->(h:Hour)`
   - Use DayOfWeek: `MATCH (d:Day)-[:IS_DAY_OF_WEEK]->(dow:DayOfWeek)`

5. **Genre Analysis:**
   - Go through Artist: `MATCH (t:Track)-[:PERFORMED_BY]->(a:Artist)-[:HAS_GENRE]->(g:Genre)`

6. **Always return useful fields:**
   - For artists: name, id, listen count
   - For tracks: name, artist names, listen count, and t.spotify_id
   - For albums: name, artist names, listen count, and al.spotify_id
   - For time analysis: the time period and counts

## Task

Generate a Cypher query to answer the following question:

Question: {query}

Additional context (if any): {context}

Respond with a JSON object:
{{
    "cypher": "the complete Cypher query",
    "explanation": "brief explanation of what the query does",
    "return_type": "single_value" | "list" | "table" | "aggregation"
}}

Only output valid JSON, no markdown."""


QUERY_REFINEMENT_PROMPT = """The following Cypher query failed or returned unexpected results:

Original question: {query}

Failed query:
```cypher
{cypher}
```

Error or issue: {error}

{schema}

Please generate a corrected Cypher query. Common issues to check:
1. Property names are case-sensitive
2. Date comparisons need proper formatting
3. Relationships must be traversed in the correct direction
4. Aggregations need proper GROUP BY (WITH clause in Cypher)

Respond with a JSON object:
{{
    "cypher": "the corrected Cypher query",
    "explanation": "what was fixed",
    "return_type": "single_value" | "list" | "table" | "aggregation"
}}

Only output valid JSON, no markdown."""
