import os
import sys
import time
import logging
from typing import Callable, Optional

import spotipy

logger = logging.getLogger(__name__)

# Ensure ingestion directory is on the path for local imports
_ingestion_dir = os.path.dirname(os.path.abspath(__file__))
if _ingestion_dir not in sys.path:
    sys.path.insert(0, _ingestion_dir)

from spotify_parser import SpotifyParser
from bigquery_db import BigQueryDatabase


def run_ingestion(
    temp_file_path: str,
    user_id: str,
    spotify_client: spotipy.Spotify,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """
    Runs the full Spotify history ingestion pipeline synchronously.

    Intended to be called from an async context via asyncio.to_thread so it
    doesn't block the FastAPI event loop.

    Args:
        temp_file_path: Absolute path to the temporary JSON file on disk.
        user_id: Spotify user ID, used to tag BigQuery rows.
        spotify_client: Authenticated spotipy.Spotify instance for the user.
        progress_callback: Optional callable(pct: int, message: str) invoked at
            key pipeline stages to report progress (0-100).

    Returns:
        dict with keys 'total_events' (int) and 'duration_seconds' (float).
    """

    def report(pct: int, msg: str):
        logger.info("[ingestion %s] %d%% — %s", user_id, pct, msg)
        if progress_callback:
            progress_callback(pct, msg)

    start_time = time.time()

    project_id = os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2")
    dataset_id = os.getenv("BQ_DATASET_ID", "timber")

    report(5, "Connecting to database...")
    db = BigQueryDatabase(project_id=project_id, dataset_id=dataset_id)
    db.connect()

    try:
        report(10, "Initializing schema...")
        db.ensure_tables()

        report(15, "Starting ingestion...")
        parser = SpotifyParser(spotify_client)
        current_user = spotify_client.current_user()

        total = 0
        batch_num = 0
        for batch in parser.parse_streaming_history_in_batches(temp_file_path):
            batch_num += 1
            for event in batch:
                db.ingest_listening_event(current_user, event)
            db.flush()
            total += len(batch)
            # Scale 15→90% — assumes ~100k events for a heavy user; saturates gracefully
            pct = min(90, 15 + int(total * 75 / 100_000))
            report(pct, f"Processed {total:,} events (batch {batch_num})...")

        duration = round(time.time() - start_time, 1)
        report(100, f"Done! {total:,} events ingested in {duration}s.")
        return {"total_events": total, "duration_seconds": duration}

    finally:
        db.close()
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.info("Removed temp file: %s", temp_file_path)
        except OSError as e:
            logger.warning("Could not remove temp file %s: %s", temp_file_path, e)
