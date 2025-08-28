import json
import re
import spotipy
from datetime import datetime, timezone, date
from spotipy import SpotifyClientCredentials, SpotifyOAuth
from typing import Dict, List, Any, Union


class SpotifyParser:
    def __init__(self, sp: Union[spotipy.Spotify, SpotifyClientCredentials, SpotifyOAuth]):
        if isinstance(sp, spotipy.Spotify):
            # Already a Spotify client instance
            self.sp = sp
        elif isinstance(sp, (SpotifyClientCredentials, SpotifyOAuth)):
            # Auth manager provided, create Spotify client
            self.sp = spotipy.Spotify(auth_manager=sp)
        else:
            raise TypeError("sp must be a Spotify client, SpotifyClientCredentials, or SpotifyOAuth instance")
        self._artist_cache = {}

    def parse_streaming_history(self, json_path: str) -> List[Dict[str, Any]]:
        filtered_data = self._preprocess_streaming_data(json_path)
        enriched_data = self._enrich_with_spotify_data(filtered_data)
        return enriched_data

    def _preprocess_streaming_data(self, json_path: str) -> List[Dict[str, Any]]:
        with open(json_path, 'r') as file:
            json_data = json.load(file)
        filtered_data = [
            item for item in json_data 
            if item.get("spotify_track_uri") is not None 
            and item.get("incognito_mode") is False
        ]
        
        # Extract track_id from spotify_track_uri
        for item in filtered_data:
            track_uri = item.get("spotify_track_uri", "")
            match = re.search(r'spotify:track:([a-zA-Z0-9]+)', track_uri)
            item["track_id"] = match.group(1) if match else None
        
        return filtered_data

    def _enrich_with_spotify_data(self, filtered_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched_data = []
        
        # Extract track IDs for batch processing
        track_ids = [item["track_id"] for item in filtered_data if item.get("track_id")]
        
        # Process in batches of 50 (Spotify API limit)
        for i in range(0, len(track_ids), 50):
            batch_ids = track_ids[i:i+50]
            batch_items = filtered_data[i:i+50]
            
            try:
                tracks_response = self.sp.tracks(batch_ids)
                
                # Get unique artist IDs for genre lookup
                artist_ids = []
                track_to_artist = {}
                
                for track in tracks_response['tracks']:
                    if track and track['artists']:
                        artist_id = track['artists'][0]['id']
                        if artist_id not in artist_ids:
                            artist_ids.append(artist_id)
                        track_to_artist[track['id']] = artist_id
                
                # Batch get artists for genres
                artist_genres_cache = {}
                for j in range(0, len(artist_ids), 50):
                    batch_artist_ids = artist_ids[j:j+50]
                    artists_response = self.sp.artists(batch_artist_ids)
                    
                    for artist in artists_response['artists']:
                        if artist:
                            genres = artist.get('genres', [])
                            artist_genres_cache[artist['id']] = genres if genres else []
                
                # Transform each item to final format
                for original_item, track in zip(batch_items, tracks_response['tracks']):
                    if track:
                        enriched_item = self._transform_to_final_format(original_item, track, artist_genres_cache)
                        enriched_data.append(enriched_item)
                    else:
                        # Fallback for unavailable tracks
                        enriched_data.append(self._create_fallback_item(original_item))
                        
            except Exception as e:
                # Fallback for entire batch
                for item in batch_items:
                    enriched_data.append(self._create_fallback_item(item))
        
        return enriched_data
    
    def _transform_to_final_format(self, original_item: Dict[str, Any], track: Dict[str, Any], artist_genres_cache: Dict[str, List[str]]) -> Dict[str, Any]:
        # Get primary artist info
        artist = track['artists'][0] if track['artists'] else {}
        album = track.get('album', {})
        
        # Get genres from cache
        artist_id = artist.get('id', '')
        genres = artist_genres_cache.get(artist_id, [])
        
        # Parse timestamp to datetime with UTC timezone
        ts_parsed = None
        if original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")
        
        # Parse album release date to date object
        release_date_parsed = None
        release_date_str = album.get('release_date')
        if release_date_str:
            try:
                # Handle different date formats (YYYY, YYYY-MM, YYYY-MM-DD)
                if len(release_date_str) == 4:  # Year only
                    release_date_parsed = datetime.strptime(release_date_str, '%Y').date()
                elif len(release_date_str) == 7:  # Year-Month
                    release_date_parsed = datetime.strptime(release_date_str, '%Y-%m').date()
                else:  # Full date
                    release_date_parsed = datetime.strptime(release_date_str, '%Y-%m-%d').date()
            except (ValueError, AttributeError):
                release_date_parsed = release_date_str
        
        return {
            "ts": ts_parsed,
            "trackId": track.get('id'),
            "track_name": track.get('name'),
            "track_url": f"https://open.spotify.com/track/{track.get('id')}" if track.get('id') else None,
            "ms_played": original_item.get("ms_played"),
            "duration_ms": track.get('duration_ms'),
            "artistId": artist.get('id'),
            "artist_name": artist.get('name'),
            "artist_url": f"https://open.spotify.com/artist/{artist.get('id')}" if artist.get('id') else None,
            "albumId": album.get('id'),
            "album_type": album.get('album_type'),
            "album_name": album.get('name'),
            "album_url": f"https://open.spotify.com/album/{album.get('id')}" if album.get('id') else None,
            "album_release_date": release_date_parsed,
            "album_total_tracks": album.get('total_tracks'),
            "genre": genres
        }
    
    def _create_fallback_item(self, original_item: Dict[str, Any]) -> Dict[str, Any]:
        # Parse timestamp to datetime with UTC timezone
        ts_parsed = None
        if original_item.get("ts"):
            try:
                ts_parsed = datetime.fromisoformat(original_item["ts"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                ts_parsed = original_item.get("ts")
        
        return {
            "ts": ts_parsed,
            "trackId": original_item.get("track_id"),
            "track_name": original_item.get("master_metadata_track_name"),
            "track_url": f"https://open.spotify.com/track/{original_item.get('track_id')}" if original_item.get('track_id') else None,
            "ms_played": original_item.get("ms_played"),
            "duration_ms": None,
            "artistId": None,
            "artist_name": original_item.get("master_metadata_album_artist_name"),
            "artist_url": None,
            "albumId": None,
            "album_type": None,
            "album_name": original_item.get("master_metadata_album_album_name"),
            "album_url": None,
            "album_release_date": None,
            "album_total_tracks": None,
            "genre": []
        }
