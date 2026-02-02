import json
import re
import sqlite3
import spotipy
from datetime import datetime, timezone
from spotipy import SpotifyClientCredentials, SpotifyOAuth
from typing import Dict, List, Any, Union, Tuple

class SpotifyParser:
    def __init__(self, sp: Union[spotipy.Spotify, SpotifyClientCredentials, SpotifyOAuth], db_file: str = "spotify_cache.db"):
        if isinstance(sp, spotipy.Spotify):
            self.sp = sp
        else:
            self.sp = spotipy.Spotify(auth_manager=sp)
        
        self.db_file = db_file
        self._init_db()
        # NOTE: We no longer load the cache into memory.

    def _init_db(self):
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, data TEXT)')
            cursor.execute('CREATE TABLE IF NOT EXISTS artists (id TEXT PRIMARY KEY, data TEXT)')
            cursor.execute('CREATE TABLE IF NOT EXISTS albums (id TEXT PRIMARY KEY, data TEXT)')
            # Indexing is crucial for speed with millions of records
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracks_id ON tracks(id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_artists_id ON artists(id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_id ON albums(id)')
            conn.commit()

    def _get_batch_from_db(self, table: str, ids: List[str]) -> Dict[str, Any]:
        """
        Fetches only the requested IDs from the database.
        Returns a dictionary {id: data}.
        """
        if not ids:
            return {}
            
        placeholders = ','.join('?' * len(ids))
        query = f"SELECT id, data FROM {table} WHERE id IN ({placeholders})"
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(query, ids)
                results = {}
                for row in cursor.fetchall():
                    results[row[0]] = json.loads(row[1])
                return results
        except sqlite3.Error as e:
            print(f"DB Read Error: {e}")
            return {}

    def _save_batch_to_db(self, new_tracks: Dict[str, Any], new_artists: Dict[str, Any], new_albums: Dict[str, Any] = None):
        """Saves new items to disk."""
        if not new_tracks and not new_artists and not new_albums:
            return

        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                if new_tracks:
                    track_data = [(tid, json.dumps(data)) for tid, data in new_tracks.items()]
                    cursor.executemany("INSERT OR IGNORE INTO tracks (id, data) VALUES (?, ?)", track_data)
                if new_artists:
                    artist_data = [(aid, json.dumps(data)) for aid, data in new_artists.items()]
                    cursor.executemany("INSERT OR IGNORE INTO artists (id, data) VALUES (?, ?)", artist_data)
                if new_albums:
                    album_data = [(alid, json.dumps(data)) for alid, data in new_albums.items()]
                    cursor.executemany("INSERT OR IGNORE INTO albums (id, data) VALUES (?, ?)", album_data)
                conn.commit()
        except sqlite3.Error as e:
            print(f"DB Write Error: {e}")

    def parse_streaming_history(self, json_path: str) -> List[Dict[str, Any]]:
        filtered_data = self._preprocess_streaming_data(json_path)
        return self._enrich_with_spotify_data(filtered_data)

    def _preprocess_streaming_data(self, json_path: str) -> List[Dict[str, Any]]:
        # This part remains the same
        with open(json_path, 'r', encoding='utf-8') as file:
            json_data = json.load(file)

        # Filter out missing URIs and zero/null play times (keep incognito mode listens)
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

    def _enrich_with_spotify_data(self, filtered_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched_data = []
        valid_items = [item for item in filtered_data if item.get("track_id")]
        
        chunk_size = 50
        print(f"Processing {len(valid_items)} items using On-Demand SQL Lookups...")
        
        for i in range(0, len(valid_items), chunk_size):
            batch_items = valid_items[i:i+chunk_size]
            batch_ids = [item["track_id"] for item in batch_items]
            
            # Temporary holders for new API data
            new_tracks_for_db = {}
            new_artists_for_db = {}
            new_albums_for_db = {}

            try:
                # --- 1. TRACKS: CHECK DB FIRST ---
                # Retrieve what we already have in DB for these 50 IDs
                known_tracks = self._get_batch_from_db('tracks', batch_ids)

                # Identify which IDs are missing from the DB result
                missing_track_ids = [tid for tid in batch_ids if tid not in known_tracks]

                # Deduplicate missing IDs
                missing_track_ids = list(set(missing_track_ids))

                if missing_track_ids:
                    try:
                        response = self.sp.tracks(missing_track_ids)
                        for track in response['tracks']:
                            if track:
                                known_tracks[track['id']] = track
                                new_tracks_for_db[track['id']] = track
                    except Exception as e:
                        print(f"Error fetching tracks: {e}")

                # Reconstruct full list of objects for the batch
                batch_tracks_objects = [known_tracks.get(tid) for tid in batch_ids]

                # --- 1.5. ALBUMS: FETCH FULL ALBUM DATA FOR UPC ---
                # Extract album IDs from track objects
                batch_album_ids = {
                    t['album']['id'] for t in batch_tracks_objects
                    if t and t.get('album') and t['album'].get('id')
                }

                batch_album_ids_list = list(batch_album_ids)
                known_albums = self._get_batch_from_db('albums', batch_album_ids_list)

                missing_album_ids = [alid for alid in batch_album_ids_list if alid not in known_albums]

                if missing_album_ids:
                    try:
                        # Fetch albums in chunks of 20 (API limit)
                        for k in range(0, len(missing_album_ids), 20):
                            chunk_album_ids = missing_album_ids[k:k+20]
                            albums_response = self.sp.albums(chunk_album_ids)
                            for album in albums_response['albums']:
                                if album:
                                    known_albums[album['id']] = album
                                    new_albums_for_db[album['id']] = album
                    except Exception as e:
                        print(f"Error fetching albums: {e}")

                # --- 2. ARTISTS: CHECK DB FIRST ---
                # Extract primary artist IDs from the track objects
                batch_artist_ids = {
                    artist['id'] for t in batch_tracks_objects if t and t.get('artists')
                    for artist in t['artists'] if artist.get('id') 
                }
                # Also extract artist IDs from the album object
                album_artist_ids = {
                    artist['id'] for t in batch_tracks_objects if t and t.get('album') and t['album'].get('artists')
                    for artist in t['album']['artists'] if artist.get('id')
                }
                batch_artist_ids.update(album_artist_ids)
                
                # Check DB for these artists
                batch_artist_ids_list = list(batch_artist_ids)
                known_artists = self._get_batch_from_db('artists', batch_artist_ids_list)
                
                missing_artist_ids = [aid for aid in batch_artist_ids_list if aid not in known_artists]
                
                if missing_artist_ids:
                    try:
                        # Chunk artist IDs because a batch of 50 tracks might yield >50 artists
                        for k in range(0, len(missing_artist_ids), 50):
                            chunk_artist_ids = missing_artist_ids[k:k+50]
                            artists_response = self.sp.artists(chunk_artist_ids)
                            for artist in artists_response['artists']:
                                if artist:
                                    genres = artist.get('genres', [])
                                    known_artists[artist['id']] = genres if genres else []
                                    new_artists_for_db[artist['id']] = genres if genres else []
                    except Exception as e:
                        print(f"Error fetching artists: {e}")

                # --- 3. SAVE NEW DATA TO DB ---
                if new_tracks_for_db or new_artists_for_db or new_albums_for_db:
                    self._save_batch_to_db(new_tracks_for_db, new_artists_for_db, new_albums_for_db)

                # --- 4. TRANSFORM ---
                for original_item, track in zip(batch_items, batch_tracks_objects):
                    if track:
                        # Get full album data if available
                        album_id = track.get('album', {}).get('id')
                        full_album = known_albums.get(album_id) if album_id else None

                        # Pass the local 'known_artists' dict and full album data
                        enriched_item = self._transform_to_final_format(original_item, track, known_artists, full_album)
                        enriched_data.append(enriched_item)
                    else:
                        enriched_data.append(self._create_fallback_item(original_item))
                        
            except Exception as e:
                print(f"Batch Error at index {i}: {e}")
                for item in batch_items:
                    enriched_data.append(self._create_fallback_item(item))
        
        return enriched_data

    # ... (Helper methods _transform_to_final_format and _create_fallback_item remain unchanged)
    def _transform_to_final_format(self, original_item: Dict[str, Any], track: Dict[str, Any], artist_cache: Dict[str, List[str]], full_album: Dict[str, Any] = None) -> Dict[str, Any]:
        artists = track.get('artists', [])
        # Use full album data if available, otherwise fall back to track's nested album
        album = full_album if full_album else track.get('album', {})
        album_artists = album.get('artists', [])
        ts_parsed = None
        # Use offline_timestamp if offline is True, otherwise use ts
        if original_item.get("offline") is True and original_item.get("offline_timestamp"):
            try:
                # offline_timestamp is a Unix timestamp in milliseconds
                ts_parsed = datetime.fromtimestamp(original_item["offline_timestamp"] / 1000, tz=timezone.utc)
            except (ValueError, TypeError, AttributeError):
                ts_parsed = None

        # Fallback to regular ts if not offline or if offline_timestamp parsing failed
        if ts_parsed is None and original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")

        release_date_parsed = None
        release_date_str = album.get('release_date')
        if release_date_str:
            try:
                if len(release_date_str) == 4:
                    release_date_parsed = datetime.strptime(release_date_str, '%Y').date()
                elif len(release_date_str) == 7:
                    release_date_parsed = datetime.strptime(release_date_str, '%Y-%m').date()
                else:
                    release_date_parsed = datetime.strptime(release_date_str, '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                release_date_parsed = release_date_str
        
        # Extract ISRC for track deduplication
        isrc = track.get('external_ids', {}).get('isrc')

        # Extract UPC for album deduplication
        upc = album.get('external_ids', {}).get('upc')

        return {
            "ts": ts_parsed,
            "trackId": track.get('id'),
            "track_name": track.get('name'),
            "track_url": f"http://open.spotify.com/track/{track.get('id')}" if track.get('id') else None,
            "ms_played": original_item.get("ms_played"),
            "duration_ms": track.get('duration_ms'),
            "skipped": original_item.get("skipped"),
            "incognito": original_item.get("incognito_mode", False),
            "isrc": isrc,
            "artists": [{
                "id": artist.get('id'),
                "name": artist.get('name'),
                "url": f"http://open.spotify.com/artist/{artist.get('id')}" if artist.get('id') else None,
                "genres": artist_cache.get(artist.get('id'), [])
            } for artist in artists],
            "albumId": album.get('id'),
            "album_type": album.get('album_type'),
            "album_name": album.get('name'),
            "album_url": f"http://open.spotify.com/album/{album.get('id')}" if album.get('id') else None,
            "album_release_date": release_date_parsed,
            "album_artists": [{
                "id": artist.get('id'),
                "name": artist.get('name'),
                "url": f"http://open.spotify.com/artist/{artist.get('id')}" if artist.get('id') else None
            } for artist in album_artists],
            "album_total_tracks": album.get('total_tracks'),
            "upc": upc
        }
    
    def _create_fallback_item(self, original_item: Dict[str, Any]) -> Dict[str, Any]:
        ts_parsed = None
        # Use offline_timestamp if offline is True, otherwise use ts
        if original_item.get("offline") is True and original_item.get("offline_timestamp"):
            try:
                # offline_timestamp is a Unix timestamp in milliseconds
                ts_parsed = datetime.fromtimestamp(original_item["offline_timestamp"] / 1000, tz=timezone.utc)
            except (ValueError, TypeError, AttributeError):
                ts_parsed = None

        # Fallback to regular ts if not offline or if offline_timestamp parsing failed
        if ts_parsed is None and original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")

        return {
            "ts": ts_parsed,
            "trackId": original_item.get("track_id"),
            "track_name": original_item.get("master_metadata_track_name"),
            "track_url": f"http://open.spotify.com/track/{original_item.get('track_id')}" if original_item.get('track_id') else None,
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
            "upc": None
        }
        