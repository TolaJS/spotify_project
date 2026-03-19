"""Lightweight ingestion for Spotify recently-played tracks.

Transforms the Spotify recently-played API response into the same schema used
by bigquery_db.ingest_listening_event so the data structure stays consistent.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _parse_release_date(release_date_str: str):
    if not release_date_str:
        return None
    try:
        if len(release_date_str) == 4:
            return datetime.strptime(release_date_str, "%Y").date()
        elif len(release_date_str) == 7:
            return datetime.strptime(release_date_str, "%Y-%m").date()
        else:
            return datetime.strptime(release_date_str, "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return release_date_str


def _transform_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Converts one recently-played item to the ingest_listening_event schema."""
    track = item["track"]
    album = track.get("album", {})

    ts = datetime.fromisoformat(item["played_at"].replace("Z", "+00:00")).replace(microsecond=0)

    # Use the track's full duration as ms_played — the recently-played endpoint
    # does not expose partial play time.
    duration_ms = track.get("duration_ms", 0)

    return {
        "ts": ts,
        "trackId": track["id"],
        "track_name": track.get("name"),
        "track_url": f"https://open.spotify.com/track/{track['id']}",
        "ms_played": duration_ms,
        "duration_ms": duration_ms,
        "skipped": False,
        "incognito": False,
        "isrc": track.get("external_ids", {}).get("isrc"),
        "artists": [
            {
                "id": a["id"],
                "name": a["name"],
                "url": f"https://open.spotify.com/artist/{a['id']}",
                # Genres are not included in recently-played responses.
                # If the artist already exists in the graph their genres are preserved;
                # new artists will have genres added on next full upload.
                "genres": [],
            }
            for a in track.get("artists", [])
        ],
        "albumId": album.get("id"),
        "album_type": album.get("album_type"),
        "album_name": album.get("name"),
        "album_url": f"https://open.spotify.com/album/{album['id']}" if album.get("id") else None,
        "album_release_date": _parse_release_date(album.get("release_date", "")),
        "album_artists": [
            {
                "id": a["id"],
                "name": a["name"],
                "url": f"https://open.spotify.com/artist/{a['id']}",
            }
            for a in album.get("artists", [])
        ],
        "album_total_tracks": album.get("total_tracks"),
        # Simplified album objects from recently-played do not include UPC.
        "upc": None,
    }


def ingest_recently_played(db, user_info: Dict[str, Any], items: List[Dict[str, Any]]) -> int:
    """Ingests a list of recently-played items into BigQuery.

    Args:
        db: Connected BigQueryDatabase instance.
        user_info: Spotify user object returned by sp.current_user().
        items: List of recently-played item dicts from the Spotify API.

    Returns:
        Number of events successfully ingested.
    """
    user_id = user_info.get("id", "unknown")
    logger.info("[recently-played][user=%s] Ingesting %d items.", user_id, len(items))

    count = 0
    skipped = 0
    for item in items:
        try:
            event_data = _transform_item(item)
            db.ingest_listening_event(user_info, event_data)
            count += 1
        except Exception as e:
            logger.warning("[recently-played][user=%s] Skipped item (played_at=%s): %s",
                           user_id, item.get("played_at"), e)
            skipped += 1

    logger.info("[recently-played][user=%s] Buffered %d events (%d skipped). Flushing to BigQuery...",
                user_id, count, skipped)
    db.flush()
    logger.info("[recently-played][user=%s] Flush complete.", user_id)
    return count
