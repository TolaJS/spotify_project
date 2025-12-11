from neo4j import GraphDatabase
from spotify_parser import SpotifyParser
from typing import List, Dict, Any, Optional


class Neo4jDatabase:
    
    def __init__(self, uri: str, auth: tuple):
        self._uri = uri
        self._auth = auth
        self._driver= None
        
    def connect(self):
        try:
            self._driver = GraphDatabase.driver(self._uri, self._auth)
            self._driver.verify_connectivity()
            print("Neo4j Database Connected!!!!")
        except Exception as e:
            print(f"Failed to Connect to Neo4j: {e}")
            self._driver = None
    
    def close(self):
        if self._driver:
            self._driver.close()
            print("Connection to Neo4j database closed.")
    
    def _execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self._driver:
            print("No active connection to Neo4j.")
            return []
        
        with self._driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]
    
    def create_constraints(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Track) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Artist) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (al:Album) REQUIRE al.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Playlist) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (le:ListenEvent) REQUIRE le.id IS UNIQUE"
        ]
        for query in queries:
            self._execute_query(query)
        print("Constraints created.")
    
    def ingest_listening_event(self, user: Dict[str, Any], event_data: Dict[str, Any]):
        query = """
        MERGE (u:User {id: $userId})
        ON CREATE SET
            u.name = $user_name,
            u.url = $user_url
        
        MERGE (t:Track {id: $trackId})
        ON CREATE SET 
            t.name = $track_name,
            t.url = $track_url,
            t.duration_ms = $duration_ms
        
        // Use UNWIND to handle multiple artists and their genres
        WITH u, t
        UNWIND $artists AS artist_data
        MERGE (a:Artist {id: artist_data.id})
        ON CREATE SET 
            a.name = artist_data.name, 
            a.url = artist_data.url
        MERGE (t)-[:PERFORMED_BY]->(a)
        
        FOREACH (gName IN artist_data.genres |
            MERGE (g:Genre {name: gName})
            MERGE (a)-[:HAS_GENRE]->(g)
        )

        WITH u, t, COLLECT(a) AS trackArtists

        // Create/update collaboration relationships with frequency count
        FOREACH (artist1 IN trackArtists |
            FOREACH (artist2 IN trackArtists |
                // Use internal node IDs to avoid self-loops and duplicate relationships
                WHERE id(artist1) < id(artist2)
                MERGE (artist1)-[r:COLLABORATED_WITH]-(artist2)
                ON CREATE SET r.count = 1
                ON MATCH SET r.count = r.count + 1
            )
        )

        // Use a CALL subquery for conditional album logic. It's cleaner than the FOREACH hack.
        CALL {
            WITH t // Importing WITH to bring t into the subquery scope
            // This subquery only executes if albumId is not null
            WHERE $albumId IS NOT NULL
            MERGE (al:Album {id: $albumId})
            ON CREATE SET
                 al.name = $album_name,
                 al.type = $album_type,
                 al.url = $album_url,
                 al.release_date = $album_release_date,
                 al.total_tracks = $album_total_tracks
            MERGE (t)-[:BELONGS_TO_ALBUM]->(al)

            // Unwind the album's primary artists and connect them to the album
            WITH al
            UNWIND $album_artists AS album_artist_data
            MERGE (aa:Artist {id: album_artist_data.id})
            ON CREATE SET aa.name = album_artist_data.name, aa.url = album_artist_data.url
            MERGE (aa)-[:HAS_ALBUM]->(al)
        }
        
        WITH u, t
        MERGE (le:ListenEvent {id: $listenEventId})
        ON CREATE SET
            le.timestamp = $ts,
            le.ms_played = $ms_played,
            le.skipped = $skipped
        
        MERGE (u)-[:PERFORMED]->(le)
        MERGE (le)-[:IS_LISTEN_OF]->(t)

        // Link the event to the time tree at both the Day and Hour level
        WITH le, le.timestamp AS event_ts
        MATCH (d:Day {date: date(event_ts)})
        MATCH (h:Hour {hour: event_ts.hour})
        MERGE (le)-[:OCCURRED_ON]->(d)
        MERGE (le)-[:OCCURRED_AT_HOUR]->(h)
        """
        
        listen_event_id = (
            f"{user.get('id')}_{event_data.get('trackId')}_{event_data.get('ts')}"
        )

        parameters = {
            "listenEventId": listen_event_id,
            "userId": user['id'],
            "user_name": user['display_name'],
            "user_url":user['external_urls']['spotify'],
            "ts": event_data.get('ts'),
            "trackId": event_data.get("trackId"),
            "skipped": event_data.get("skipped"),
            "track_name": event_data.get("track_name"),
            "track_url":  event_data.get("track_url"),
            "ms_played": event_data.get("ms_played"),
            "duration_ms": event_data.get("duration_ms"),
            "artists": event_data.get("artists", []),
            "albumId": event_data.get("albumId"),
            "album_type": event_data.get("album_type"),
            "album_name": event_data.get("album_name"),
            "album_url": event_data.get("album_url"),
            "album_release_date": event_data.get("album_release_date"),
            "album_artists": event_data.get("album_artists", []),
            "album_total_tracks": event_data.get("album_total_tracks")
        }

        self._execute_query(query, parameters)

    def get_user_playlist(self):
        pass

    def create_time_tree(self):
        print("Creating time tree in Neo4j...")

        # This query is idempotent. It will only create nodes and relationships that don't already exist.
        # It covers the range from Jan 2008 (the year Spotify launched) to Dec 2035.

        # Part 1: Create the static DayOfWeek nodes first for efficiency.
        dow_query = """
        UNWIND [
            {day: 1, name: 'Monday'}, {day: 2, name: 'Tuesday'}, {day: 3, name: 'Wednesday'},
            {day: 4, name: 'Thursday'}, {day: 5, name: 'Friday'}, {day: 6, name: 'Saturday'},
            {day: 7, name: 'Sunday'}
        ] AS dow_data
        MERGE (dow:DayOfWeek {day: dow_data.day})
        ON CREATE SET dow.name = dow_data.name
        """
        self._execute_query(dow_query)
        print("-> DayOfWeek nodes ensured.")

        # Part 1.5: Create the static Hour nodes (0-23).
        hour_query = """
        UNWIND range(0, 23) AS h
        MERGE (:Hour {hour: h})
        """
        self._execute_query(hour_query)
        print("-> Hour nodes ensured.")

        # Part 2: Generate the full time tree.
        time_tree_query = """
        WITH date('2008-01-01') AS startDate, date('2035-12-31') AS endDate
        // Generate a list of all dates in the range
        WITH [d IN range(0, duration.inDays(startDate, endDate).days + 1) | startDate + duration({days: d})] AS dates
        UNWIND dates AS d

        // Create or find Year, Month, and Day nodes
        MERGE (year:Year {year: d.year})
        MERGE (month:Month {month: d.month})
        ON CREATE SET month.name = d.monthName
        MERGE (day:Day {date: d})
        ON CREATE SET day.day = d.day

        // Create relationships between time nodes
        MERGE (year)-[:HAS_MONTH]->(month)
        MERGE (month)-[:HAS_DAY]->(day)

        // Link the Day to its corresponding DayOfWeek
        WITH day, d
        MATCH (dow:DayOfWeek {day: d.dayOfWeek})
        MERGE (day)-[:IS_DAY_OF_WEEK]->(dow)
        """
        self._execute_query(time_tree_query)
        print("-> Time tree from 2008 to 2035 created/verified successfully.")