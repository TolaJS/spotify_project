"""BigQuery database layer for Timber — replaces neo4j_db.py.

Buffers all rows in memory during ingestion then writes them in one
bulk MERGE per table (load-job → MERGE → drop temp table), ensuring
idempotent upserts and efficient batch writes.
"""

import json
import logging
import os
import time
import uuid
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

logger = logging.getLogger(__name__)

DATASET_ID = "timber"


def _to_bq_timestamp(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _to_bq_date(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        if len(val) == 4:
            return f"{val}-01-01"
        if len(val) == 7:
            return f"{val}-01"
        return val
    return str(val)


class BigQueryDatabase:
    """BigQuery client with buffered batch ingestion.

    Usage:
        db = BigQueryDatabase(project_id="my-project")
        db.connect()
        db.ensure_tables()
        for event in events:
            db.ingest_listening_event(user, event)
        db.flush()   # writes everything to BigQuery
        db.close()
    """

    _SCHEMAS: Dict[str, List[bigquery.SchemaField]] = {
        "listening_events": [
            bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ts", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("track_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ms_played", "INT64"),
            bigquery.SchemaField("duration_ms", "INT64"),
            bigquery.SchemaField("is_valid_listen", "BOOL"),
            bigquery.SchemaField("is_full_listen", "BOOL"),
            bigquery.SchemaField("skipped", "BOOL"),
            bigquery.SchemaField("incognito", "BOOL"),
        ],
        "tracks": [
            bigquery.SchemaField("track_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("track_name", "STRING"),
            bigquery.SchemaField("track_url", "STRING"),
            bigquery.SchemaField("duration_ms", "INT64"),
            bigquery.SchemaField("isrc", "STRING"),
            bigquery.SchemaField("spotify_id", "STRING"),
        ],
        "artists": [
            bigquery.SchemaField("artist_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("artist_name", "STRING"),
            bigquery.SchemaField("artist_url", "STRING"),
        ],
        "track_artists": [
            bigquery.SchemaField("track_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("artist_id", "STRING", mode="REQUIRED"),
        ],
        "albums": [
            bigquery.SchemaField("album_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("album_name", "STRING"),
            bigquery.SchemaField("album_type", "STRING"),
            bigquery.SchemaField("album_url", "STRING"),
            bigquery.SchemaField("release_date", "DATE"),
            bigquery.SchemaField("total_tracks", "INT64"),
            bigquery.SchemaField("upc", "STRING"),
            bigquery.SchemaField("spotify_id", "STRING"),
        ],
        "track_albums": [
            bigquery.SchemaField("track_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("album_id", "STRING", mode="REQUIRED"),
        ],
        "artist_genres": [
            bigquery.SchemaField("artist_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("genre", "STRING", mode="REQUIRED"),
        ],
        "album_artists": [
            bigquery.SchemaField("album_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("artist_id", "STRING", mode="REQUIRED"),
        ],
    }

    def __init__(self, project_id: str, dataset_id: str = DATASET_ID, location: str = "US"):
        self._project_id = project_id
        self._dataset_id = dataset_id
        self._location = location
        self._client: Optional[bigquery.Client] = None

        # Ingestion buffers — keyed dicts deduplicate in Python before the BQ MERGE
        self._events: List[Dict] = []
        self._tracks: Dict[str, Dict] = {}
        self._artists: Dict[str, Dict] = {}
        self._albums: Dict[str, Dict] = {}
        self._track_artists: set = set()
        self._track_albums: set = set()
        self._artist_genres: set = set()
        self._album_artists: set = set()

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def connect(self):
        self._client = bigquery.Client(project=self._project_id)
        logger.info("BigQuery client initialised for %s.%s", self._project_id, self._dataset_id)

    def close(self):
        if self._client:
            self._client.close()

    def ensure_tables(self):
        """Create the dataset and all tables if they do not already exist."""
        dataset_ref = bigquery.Dataset(f"{self._project_id}.{self._dataset_id}")
        dataset_ref.location = self._location
        self._client.create_dataset(dataset_ref, exists_ok=True)

        for table_name, schema in self._SCHEMAS.items():
            table_ref = self._client.dataset(self._dataset_id).table(table_name)
            table = bigquery.Table(table_ref, schema=schema)
            if table_name == "listening_events":
                table.time_partitioning = bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
                    field="ts",
                )
                table.clustering_fields = ["user_id"]
            self._client.create_table(table, exists_ok=True)

        logger.info("BigQuery tables ensured in %s.%s", self._project_id, self._dataset_id)

    # ── Buffering ───────────────────────────────────────────────────────────────

    def ingest_listening_event(self, user: Dict[str, Any], event_data: Dict[str, Any]):
        """Buffer a single listening event. Call flush() when done to write to BigQuery."""
        if not event_data.get("track_name"):
            return

        track_id = event_data.get("isrc") or event_data.get("trackId")
        if not track_id:
            return

        ms_played = event_data.get("ms_played", 0) or 0
        event_id = f"{user['id']}_{event_data.get('trackId')}_{event_data.get('ts')}"

        self._events.append({
            "event_id": event_id,
            "user_id": user["id"],
            "ts": _to_bq_timestamp(event_data.get("ts")),
            "track_id": track_id,
            "ms_played": ms_played,
            "duration_ms": event_data.get("duration_ms"),
            "is_valid_listen": ms_played >= 10000,
            "is_full_listen": ms_played >= 30000,
            "skipped": event_data.get("skipped"),
            "incognito": event_data.get("incognito", False),
        })

        if track_id not in self._tracks:
            self._tracks[track_id] = {
                "track_id": track_id,
                "track_name": event_data.get("track_name"),
                "track_url": event_data.get("track_url"),
                "duration_ms": event_data.get("duration_ms"),
                "isrc": event_data.get("isrc"),
                "spotify_id": event_data.get("trackId"),
            }

        for artist in event_data.get("artists", []):
            artist_id = artist.get("id")
            if not artist_id:
                continue
            if artist_id not in self._artists:
                self._artists[artist_id] = {
                    "artist_id": artist_id,
                    "artist_name": artist.get("name"),
                    "artist_url": artist.get("url"),
                }
            self._track_artists.add((track_id, artist_id))
            for genre in artist.get("genres", []):
                if genre:
                    self._artist_genres.add((artist_id, genre))

        album_id = event_data.get("upc") or event_data.get("albumId")
        if album_id:
            if album_id not in self._albums:
                self._albums[album_id] = {
                    "album_id": album_id,
                    "album_name": event_data.get("album_name"),
                    "album_type": event_data.get("album_type"),
                    "album_url": event_data.get("album_url"),
                    "release_date": _to_bq_date(event_data.get("album_release_date")),
                    "total_tracks": event_data.get("album_total_tracks"),
                    "upc": event_data.get("upc"),
                    "spotify_id": event_data.get("albumId"),
                }
            self._track_albums.add((track_id, album_id))
            for aa in event_data.get("album_artists", []):
                aa_id = aa.get("id")
                if aa_id:
                    if aa_id not in self._artists:
                        self._artists[aa_id] = {
                            "artist_id": aa_id,
                            "artist_name": aa.get("name"),
                            "artist_url": aa.get("url"),
                        }
                    self._album_artists.add((album_id, aa_id))

    # ── Flushing ────────────────────────────────────────────────────────────────

    def flush(self):
        """Write all buffered rows to BigQuery using temp-table MERGE (idempotent upserts)."""
        if not self._client:
            raise RuntimeError("Not connected to BigQuery.")

        deduped_events = list({e["event_id"]: e for e in self._events}.values())
        n_dupes = len(self._events) - len(deduped_events)
        if n_dupes:
            logger.info("[bq][flush] Deduplicated %d duplicate event(s) before MERGE.", n_dupes)

        tables = [
            # (name, schema, rows, key_cols, update_cols)
            ("tracks", self._SCHEMAS["tracks"],
             list(self._tracks.values()), ["track_id"],
             ["track_name", "track_url", "duration_ms", "isrc", "spotify_id"]),
            ("artists", self._SCHEMAS["artists"],
             list(self._artists.values()), ["artist_id"],
             ["artist_name", "artist_url"]),
            ("albums", self._SCHEMAS["albums"],
             list(self._albums.values()), ["album_id"],
             ["album_name", "album_type", "album_url", "release_date", "total_tracks", "upc", "spotify_id"]),
            ("track_artists", self._SCHEMAS["track_artists"],
             [{"track_id": t, "artist_id": a} for t, a in self._track_artists],
             ["track_id", "artist_id"], None),
            ("track_albums", self._SCHEMAS["track_albums"],
             [{"track_id": t, "album_id": a} for t, a in self._track_albums],
             ["track_id", "album_id"], None),
            ("artist_genres", self._SCHEMAS["artist_genres"],
             [{"artist_id": a, "genre": g} for a, g in self._artist_genres],
             ["artist_id", "genre"], None),
            ("album_artists", self._SCHEMAS["album_artists"],
             [{"album_id": al, "artist_id": ar} for al, ar in self._album_artists],
             ["album_id", "artist_id"], None),
            # listening_events last so dimensions exist before events reference them
            ("listening_events", self._SCHEMAS["listening_events"],
             deduped_events, ["event_id"],
             ["ms_played", "is_valid_listen", "is_full_listen", "skipped", "incognito"]),
        ]

        t_flush = time.monotonic()
        total_rows = 0
        for name, schema, rows, key_cols, update_cols in tables:
            if rows:
                logger.info("[bq][flush] Merging %d rows → %s", len(rows), name)
                self._merge_table(name, schema, rows, key_cols, update_cols)
                total_rows += len(rows)

        self._events.clear()
        self._tracks.clear()
        self._artists.clear()
        self._albums.clear()
        self._track_artists.clear()
        self._track_albums.clear()
        self._artist_genres.clear()
        self._album_artists.clear()

        logger.info("[bq][flush] Complete. %d total rows written in %.1fs.",
                    total_rows, time.monotonic() - t_flush)

    def _merge_table(
        self,
        table_name: str,
        schema: List[bigquery.SchemaField],
        rows: List[Dict],
        key_cols: List[str],
        update_cols: Optional[List[str]],
    ):
        """Load rows into a disposable temp table then MERGE into the target table."""
        temp_id = f"{self._project_id}.{self._dataset_id}.tmp_{table_name}_{uuid.uuid4().hex[:8]}"
        target = f"`{self._project_id}.{self._dataset_id}.{table_name}`"

        ndjson = "\n".join(json.dumps(row, default=str) for row in rows).encode()
        load_cfg = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition="WRITE_TRUNCATE",
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        )
        try:
            t0 = time.monotonic()
            load_job = self._client.load_table_from_file(
                BytesIO(ndjson), temp_id, job_config=load_cfg
            )
            load_job.result()
            logger.info("[bq][merge][%s] Load job complete (job_id=%s) in %.1fs.",
                        table_name, load_job.job_id, time.monotonic() - t0)

            col_names = [f.name for f in schema]
            key_cond = " AND ".join(f"T.{c} = S.{c}" for c in key_cols)
            ins_cols = ", ".join(col_names)
            ins_vals = ", ".join(f"S.{c}" for c in col_names)
            update_clause = (
                f"WHEN MATCHED THEN UPDATE SET {', '.join(f'T.{c} = S.{c}' for c in update_cols)}"
                if update_cols
                else ""
            )
            merge_sql = f"""
                MERGE {target} T
                USING `{temp_id}` S ON {key_cond}
                {update_clause}
                WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})
            """
            t1 = time.monotonic()
            merge_job = self._client.query(merge_sql)
            merge_job.result()
            logger.info("[bq][merge][%s] MERGE complete (job_id=%s) in %.1fs. rows_affected=%s",
                        table_name, merge_job.job_id,
                        time.monotonic() - t1,
                        merge_job.num_dml_affected_rows)
        except Exception:
            logger.exception("[bq][merge][%s] MERGE failed. temp_table=%s", table_name, temp_id)
            raise
        finally:
            self._client.delete_table(temp_id, not_found_ok=True)
            logger.debug("[bq][merge][%s] Temp table dropped: %s", table_name, temp_id)

    # ── Query / Admin ───────────────────────────────────────────────────────────

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Run a read-only SQL query and return results as a list of dicts."""
        if not self._client:
            return []
        job = self._client.query(sql)
        return [dict(row) for row in job.result()]

    def user_has_data(self, user_id: str) -> bool:
        """Return True if the user has any listening events in BigQuery."""
        safe = user_id.replace("'", "\\'")
        sql = f"""
            SELECT COUNT(*) AS total
            FROM `{self._project_id}.{self._dataset_id}.listening_events`
            WHERE user_id = '{safe}'
            LIMIT 1
        """
        result = self.execute_query(sql)
        return bool(result and result[0].get("total", 0) > 0)

    def delete_user_data(self, user_id: str):
        """Delete all listening events for a user (dimension rows are shared, not deleted)."""
        safe = user_id.replace("'", "\\'")
        self._client.query(
            f"DELETE FROM `{self._project_id}.{self._dataset_id}.listening_events`"
            f" WHERE user_id = '{safe}'"
        ).result()
        logger.info("Deleted listening events for user %s", user_id)
