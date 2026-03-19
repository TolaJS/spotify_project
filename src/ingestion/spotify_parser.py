import json
import logging
import os
import re
import time
import spotipy
from datetime import datetime, timezone
from spotipy import SpotifyClientCredentials, SpotifyOAuth
from typing import Dict, List, Any, Union, Tuple, Optional

logger = logging.getLogger(__name__)


class SpotifyParser:
    def __init__(
        self,
        sp: Union[spotipy.Spotify, SpotifyClientCredentials, SpotifyOAuth],
        project_id: str = None,
        dataset_id: str = None,
    ):
        if isinstance(sp, spotipy.Spotify):
            self.sp = sp
        else:
            self.sp = spotipy.Spotify(auth_manager=sp)

        self._project_id = project_id or os.getenv("GCP_PROJECT_ID", "portfolio-projects-b1cf2")
        self._dataset_id = dataset_id or os.getenv("BQ_DATASET_ID", "timber")
        self._bq_client = None

    def _get_bq_client(self):
        if self._bq_client is None:
            from google.cloud import bigquery
            self._bq_client = bigquery.Client(project=self._project_id)
        return self._bq_client

    def parse_streaming_history(self, json_path: str) -> List[Dict[str, Any]]:
        filtered_data = self._preprocess_streaming_data(json_path)
        return self._enrich_with_data(filtered_data)

    def parse_streaming_history_in_batches(
        self, json_path: str, batch_size: int = 5000
    ):
        """Stream-parse the combined JSON file in batches to limit RAM usage.

        Yields lists of enriched event dicts, each at most ``batch_size`` long.
        A persistent track/artist/album cache is maintained across batches so
        metadata for a previously-seen track is never re-fetched.
        """
        import ijson

        track_cache: Dict[str, Any] = {}
        artist_cache: Dict[str, Any] = {}
        album_cache: Dict[str, Any] = {}

        batch: List[Dict[str, Any]] = []

        with open(json_path, "rb") as f:
            for item in ijson.items(f, "item"):
                if not item.get("spotify_track_uri") or not item.get("ms_played"):
                    continue
                match = re.search(r"spotify:track:([a-zA-Z0-9]+)", item.get("spotify_track_uri", ""))
                if not match:
                    continue
                item["track_id"] = match.group(1)
                batch.append(item)

                if len(batch) >= batch_size:
                    yield self._enrich_batch(batch, track_cache, artist_cache, album_cache)
                    batch = []

        if batch:
            yield self._enrich_batch(batch, track_cache, artist_cache, album_cache)

    def _enrich_batch(
        self,
        items: List[Dict[str, Any]],
        track_cache: Dict[str, Any],
        artist_cache: Dict[str, Any],
        album_cache: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Enrich a single batch, updating the shared caches in place."""
        t0 = time.monotonic()
        unique_new_ids = list({item["track_id"] for item in items if item["track_id"] not in track_cache})
        logger.info("[parser][batch] Enriching %d events. %d new track IDs (cache size: %d).",
                    len(items), len(unique_new_ids), len(track_cache))

        if unique_new_ids:
            bq_tracks, bq_artists, bq_albums = self._fetch_from_bigquery(unique_new_ids)
            track_cache.update(bq_tracks)
            artist_cache.update(bq_artists)
            album_cache.update(bq_albums)

            still_missing = [tid for tid in unique_new_ids if tid not in track_cache]
            if still_missing and self.sp:
                api_tracks, api_artists, api_albums = self._fetch_from_api(still_missing)
                track_cache.update(api_tracks)
                artist_cache.update(api_artists)
                album_cache.update(api_albums)

        enriched = []
        fallback_count = 0
        for item in items:
            tid = item.get("track_id")
            track = track_cache.get(tid)
            if track:
                album_id = track.get("album", {}).get("id")
                enriched.append(
                    self._transform_to_final_format(item, track, artist_cache, album_cache.get(album_id) if album_id else None)
                )
            else:
                enriched.append(self._create_fallback_item(item))
                fallback_count += 1

        logger.info("[parser][batch] Batch complete in %.1fs. enriched=%d fallback=%d",
                    time.monotonic() - t0, len(enriched) - fallback_count, fallback_count)
        return enriched

    def _preprocess_streaming_data(self, json_path: str) -> List[Dict[str, Any]]:
        with open(json_path, 'r', encoding='utf-8') as file:
            json_data = json.load(file)

        filtered_data = [
            item for item in json_data
            if item.get("spotify_track_uri") is not None
            and item.get("ms_played") is not None
            and item.get("ms_played") != 0
        ]
        for item in filtered_data:
            track_uri = item.get("spotify_track_uri", "")
            match = re.search(r'spotify:track:([a-zA-Z0-9]+)', track_uri)
            item["track_id"] = match.group(1) if match else None
        return filtered_data

    def _enrich_with_data(self, filtered_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid_items = [item for item in filtered_data if item.get("track_id")]
        unique_track_ids = list(set(item["track_id"] for item in valid_items))

        if not unique_track_ids:
            return [self._create_fallback_item(item) for item in filtered_data]

        # 1. Look up all track IDs in BigQuery (data from previous ingestions)
        bq_tracks, bq_artists, bq_albums = self._fetch_from_bigquery(unique_track_ids)

        # 2. Fetch anything not found in BigQuery from the Spotify API
        missing_ids = [tid for tid in unique_track_ids if tid not in bq_tracks]
        if missing_ids and self.sp:
            logger.info("[parser] %d/%d unique tracks not in BQ cache — fetching from Spotify API.",
                        len(missing_ids), len(unique_track_ids))
            api_tracks, api_artists, api_albums = self._fetch_from_api(missing_ids)
            bq_tracks.update(api_tracks)
            bq_artists.update(api_artists)
            bq_albums.update(api_albums)

        # 3. Build enriched events
        enriched_data = []
        for item in valid_items:
            tid = item.get("track_id")
            track = bq_tracks.get(tid)
            if track:
                album_id = track.get("album", {}).get("id")
                full_album = bq_albums.get(album_id) if album_id else None
                enriched_data.append(
                    self._transform_to_final_format(item, track, bq_artists, full_album)
                )
            else:
                enriched_data.append(self._create_fallback_item(item))

        return enriched_data

    # ── BigQuery lookup ─────────────────────────────────────────────────────────

    def _fetch_from_bigquery(
        self, track_ids: List[str]
    ) -> Tuple[Dict, Dict, Dict]:
        """Query BigQuery for previously ingested track metadata.

        Returns:
            tracks:  {spotify_track_id -> Spotify-API-compatible track dict}
            artists: {artist_id -> [genre, ...]}
            albums:  {spotify_album_id -> Spotify-API-compatible album dict}
        """
        if not track_ids:
            return {}, {}, {}

        logger.info("[parser][bq] Looking up %d track IDs in BigQuery...", len(track_ids))
        t0 = time.monotonic()

        try:
            client = self._get_bq_client()
            ds = f"`{self._project_id}.{self._dataset_id}`"
            ids_str = ", ".join(f"'{tid}'" for tid in track_ids)

            # ── Query 1: tracks + their album ───────────────────────────────
            track_rows = list(client.query(f"""
                SELECT
                    t.spotify_id  AS track_spotify_id,
                    t.track_id    AS bq_track_id,
                    t.track_name, t.duration_ms, t.isrc,
                    alb.spotify_id                    AS album_spotify_id,
                    alb.album_id                      AS bq_album_id,
                    alb.album_name, alb.album_type,
                    CAST(alb.release_date AS STRING)  AS release_date,
                    alb.total_tracks, alb.upc
                FROM {ds}.tracks t
                LEFT JOIN {ds}.track_albums tal ON t.track_id  = tal.track_id
                LEFT JOIN {ds}.albums       alb ON tal.album_id = alb.album_id
                WHERE t.spotify_id IN ({ids_str})
            """).result())

            if not track_rows:
                return {}, {}, {}

            tracks: Dict[str, Any] = {}
            bq_track_id_map: Dict[str, str] = {}  # bq_track_id -> spotify_track_id
            bq_album_ids: set = set()

            for row in track_rows:
                tid = row.track_spotify_id
                if tid and tid not in tracks:
                    tracks[tid] = {
                        "id": tid,
                        "name": row.track_name,
                        "duration_ms": row.duration_ms,
                        "external_ids": {"isrc": row.isrc},
                        "album": {"id": row.album_spotify_id},
                        "artists": [],
                    }
                    if row.bq_track_id:
                        bq_track_id_map[row.bq_track_id] = tid
                if row.bq_album_id:
                    bq_album_ids.add(row.bq_album_id)

            # ── Query 2: track artists ───────────────────────────────────────
            artist_ids: set = set()
            if bq_track_id_map:
                bq_ids_str = ", ".join(f"'{k}'" for k in bq_track_id_map)
                artist_rows = list(client.query(f"""
                    SELECT ta.track_id AS bq_track_id,
                           a.artist_id, a.artist_name
                    FROM {ds}.track_artists ta
                    JOIN {ds}.artists a ON ta.artist_id = a.artist_id
                    WHERE ta.track_id IN ({bq_ids_str})
                """).result())

                for row in artist_rows:
                    spotify_id = bq_track_id_map.get(row.bq_track_id)
                    if spotify_id and spotify_id in tracks:
                        tracks[spotify_id]["artists"].append(
                            {"id": row.artist_id, "name": row.artist_name}
                        )
                        artist_ids.add(row.artist_id)

            # ── Query 3: artist genres ───────────────────────────────────────
            artists: Dict[str, List[str]] = {}
            if artist_ids:
                aid_str = ", ".join(f"'{a}'" for a in artist_ids)
                genre_rows = list(client.query(f"""
                    SELECT artist_id, genre
                    FROM {ds}.artist_genres
                    WHERE artist_id IN ({aid_str})
                """).result())
                for row in genre_rows:
                    artists.setdefault(row.artist_id, []).append(row.genre)

            # ── Query 4: albums + album artists ─────────────────────────────
            albums: Dict[str, Any] = {}
            if bq_album_ids:
                alb_ids_str = ", ".join(f"'{a}'" for a in bq_album_ids)
                album_rows = list(client.query(f"""
                    SELECT alb.spotify_id AS album_spotify_id,
                           alb.album_name, alb.album_type,
                           CAST(alb.release_date AS STRING) AS release_date,
                           alb.total_tracks, alb.upc,
                           a.artist_id, a.artist_name
                    FROM {ds}.albums alb
                    LEFT JOIN {ds}.album_artists aa ON alb.album_id = aa.album_id
                    LEFT JOIN {ds}.artists       a  ON aa.artist_id  = a.artist_id
                    WHERE alb.album_id IN ({alb_ids_str})
                """).result())

                for row in album_rows:
                    alb_id = row.album_spotify_id
                    if not alb_id:
                        continue
                    if alb_id not in albums:
                        albums[alb_id] = {
                            "id": alb_id,
                            "name": row.album_name,
                            "album_type": row.album_type,
                            "release_date": row.release_date,
                            "total_tracks": row.total_tracks,
                            "external_ids": {"upc": row.upc},
                            "artists": [],
                        }
                    if row.artist_id:
                        existing = albums[alb_id]["artists"]
                        if not any(a["id"] == row.artist_id for a in existing):
                            existing.append({"id": row.artist_id, "name": row.artist_name})

            logger.info("[parser][bq] Lookup complete in %.1fs. tracks=%d artists=%d albums=%d",
                        time.monotonic() - t0, len(tracks), len(artists), len(albums))
            return tracks, artists, albums

        except Exception as e:
            logger.warning("[parser][bq] Lookup failed after %.1fs, falling back to Spotify API: %s",
                           time.monotonic() - t0, e)
            return {}, {}, {}

    # ── Spotify API fallback ────────────────────────────────────────────────────

    def _fetch_from_api(
        self, track_ids: List[str]
    ) -> Tuple[Dict, Dict, Dict]:
        """Fetch metadata for tracks not found in BigQuery."""
        logger.info("[parser][api] Fetching metadata for %d tracks from Spotify API.", len(track_ids))
        t0 = time.monotonic()

        tracks: Dict[str, Any] = {}
        artists: Dict[str, List[str]] = {}
        albums: Dict[str, Any] = {}

        artist_ids_to_fetch: set = set()
        fetched_tracks: List[Any] = []

        # Tracks (50 per call)
        for i in range(0, len(track_ids), 50):
            chunk = track_ids[i:i + 50]
            try:
                response = self.sp.tracks(chunk)
                for track in response["tracks"]:
                    if track:
                        fetched_tracks.append(track)
                        for artist in track.get("artists", []):
                            artist_ids_to_fetch.add(artist["id"])
            except Exception as e:
                logger.warning("[parser][api] Error fetching tracks chunk %d-%d: %s", i, i + len(chunk), e)

        logger.info("[parser][api] Fetched %d tracks. Now fetching albums...", len(fetched_tracks))

        # Albums (20 per call)
        album_ids = {
            t["album"]["id"]
            for t in fetched_tracks
            if t.get("album") and t["album"].get("id")
        }
        fetched_albums: Dict[str, Any] = {}
        album_ids_list = list(album_ids)
        for i in range(0, len(album_ids_list), 20):
            chunk = album_ids_list[i:i + 20]
            try:
                response = self.sp.albums(chunk)
                for album in response["albums"]:
                    if album:
                        fetched_albums[album["id"]] = album
                        for artist in album.get("artists", []):
                            artist_ids_to_fetch.add(artist["id"])
            except Exception as e:
                logger.warning("[parser][api] Error fetching albums chunk %d-%d: %s", i, i + len(chunk), e)

        logger.info("[parser][api] Fetched %d albums. Now fetching %d artists/genres...",
                    len(fetched_albums), len(artist_ids_to_fetch))

        # Artists / genres (50 per call)
        artist_ids_list = list(artist_ids_to_fetch)
        for i in range(0, len(artist_ids_list), 50):
            chunk = artist_ids_list[i:i + 50]
            try:
                response = self.sp.artists(chunk)
                for artist in response["artists"]:
                    if artist:
                        artists[artist["id"]] = artist.get("genres", [])
            except Exception as e:
                logger.warning("[parser][api] Error fetching artists chunk %d-%d: %s", i, i + len(chunk), e)

        logger.info("[parser][api] API fetch complete in %.1fs. tracks=%d albums=%d artists=%d",
                    time.monotonic() - t0, len(fetched_tracks), len(fetched_albums), len(artists))

        # Build track dicts in Spotify-API format
        for track in fetched_tracks:
            tid = track["id"]
            alb_simple = track.get("album", {})
            alb_full = fetched_albums.get(alb_simple.get("id"), alb_simple)
            tracks[tid] = {
                "id": tid,
                "name": track.get("name"),
                "duration_ms": track.get("duration_ms"),
                "external_ids": track.get("external_ids", {}),
                "album": {"id": alb_full.get("id")},
                "artists": [{"id": a.get("id"), "name": a.get("name")} for a in track.get("artists", [])],
            }
            alb_id = alb_full.get("id")
            if alb_id and alb_id not in albums:
                albums[alb_id] = {
                    "id": alb_id,
                    "name": alb_full.get("name"),
                    "album_type": alb_full.get("album_type"),
                    "release_date": alb_full.get("release_date"),
                    "total_tracks": alb_full.get("total_tracks"),
                    "external_ids": alb_full.get("external_ids", {}),
                    "artists": [{"id": a.get("id"), "name": a.get("name")} for a in alb_full.get("artists", [])],
                }

        return tracks, artists, albums

    # ── Transform helpers ───────────────────────────────────────────────────────

    def _transform_to_final_format(
        self,
        original_item: Dict[str, Any],
        track: Dict[str, Any],
        artist_cache: Dict[str, List[str]],
        full_album: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        album = full_album or {}
        artists = track.get("artists", [])
        album_artists = album.get("artists", [])

        ts_parsed = None
        if original_item.get("offline") is True and original_item.get("offline_timestamp"):
            try:
                ts_parsed = datetime.fromtimestamp(
                    original_item["offline_timestamp"] / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError, AttributeError):
                ts_parsed = None

        if ts_parsed is None and original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")

        release_date_parsed = None
        release_date_str = album.get("release_date")
        if release_date_str:
            try:
                if len(release_date_str) == 4:
                    release_date_parsed = datetime.strptime(release_date_str, "%Y").date()
                elif len(release_date_str) == 7:
                    release_date_parsed = datetime.strptime(release_date_str, "%Y-%m").date()
                else:
                    release_date_parsed = datetime.strptime(release_date_str, "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                release_date_parsed = release_date_str

        return {
            "ts": ts_parsed,
            "trackId": track.get("id"),
            "track_name": track.get("name"),
            "track_url": f"http://open.spotify.com/track/{track.get('id')}" if track.get("id") else None,
            "ms_played": original_item.get("ms_played"),
            "duration_ms": track.get("duration_ms"),
            "skipped": original_item.get("skipped"),
            "incognito": original_item.get("incognito_mode", False),
            "isrc": track.get("external_ids", {}).get("isrc"),
            "artists": [{
                "id": a.get("id"),
                "name": a.get("name"),
                "url": f"http://open.spotify.com/artist/{a.get('id')}" if a.get("id") else None,
                "genres": artist_cache.get(a.get("id"), []),
            } for a in artists],
            "albumId": album.get("id"),
            "album_type": album.get("album_type"),
            "album_name": album.get("name"),
            "album_url": f"http://open.spotify.com/album/{album.get('id')}" if album.get("id") else None,
            "album_release_date": release_date_parsed,
            "album_artists": [{
                "id": a.get("id"),
                "name": a.get("name"),
                "url": f"http://open.spotify.com/artist/{a.get('id')}" if a.get("id") else None,
            } for a in album_artists],
            "album_total_tracks": album.get("total_tracks"),
            "upc": album.get("external_ids", {}).get("upc"),
        }

    def _create_fallback_item(self, original_item: Dict[str, Any]) -> Dict[str, Any]:
        ts_parsed = None
        if original_item.get("offline") is True and original_item.get("offline_timestamp"):
            try:
                ts_parsed = datetime.fromtimestamp(
                    original_item["offline_timestamp"] / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError, AttributeError):
                ts_parsed = None

        if ts_parsed is None and original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")

        return {
            "ts": ts_parsed,
            "trackId": original_item.get("track_id"),
            "track_name": original_item.get("master_metadata_track_name"),
            "track_url": f"http://open.spotify.com/track/{original_item.get('track_id')}" if original_item.get("track_id") else None,
            "ms_played": original_item.get("ms_played"),
            "duration_ms": None,
            "skipped": False,
            "incognito": original_item.get("incognito_mode", False),
            "isrc": None,
            "artists": [],
            "albumId": None,
            "album_type": None,
            "album_name": original_item.get("master_metadata_album_album_name"),
            "album_url": None,
            "album_release_date": None,
            "album_artists": [],
            "album_total_tracks": None,
            "upc": None,
        }
