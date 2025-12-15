import re
import logging
from typing import Optional, Dict, Any, List
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)


class SpotifyIntegration:
    URI_PATTERN = re.compile(r'spotify:(track|playlist|album|artist):([a-zA-Z0-9]+)')
    URL_PATTERN = re.compile(r'open\.spotify\.com/(track|playlist|album|artist)/([a-zA-Z0-9]+)')

    def __init__(self, client_id: str, client_secret: str):
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
        logger.info("Spotify client initialized")

    def parse_uri(self, uri_or_url: str) -> Optional[Dict[str, str]]:
        match = self.URI_PATTERN.search(uri_or_url) or self.URL_PATTERN.search(uri_or_url)
        if match:
            return {'type': match.group(1), 'id': match.group(2)}
        return None

    def get_track_info(self, track_uri: str) -> Optional[Dict[str, Any]]:
        parsed = self.parse_uri(track_uri)
        if not parsed or parsed['type'] != 'track':
            return None

        try:
            return self.sp.track(parsed['id'])
        except Exception as e:
            logger.error(f"Error getting track info: {e}")
            return None

    def _get_tracks_from_collection(self, uri: str, expected_type: str) -> List[Dict[str, Any]]:
        parsed = self.parse_uri(uri)
        if not parsed or parsed['type'] != expected_type:
            return []

        try:
            if expected_type == 'playlist':
                collection = self.sp.playlist(parsed['id'])
            elif expected_type == 'album':
                collection = self.sp.album(parsed['id'])
            else:
                return []

            if not collection:
                return []
            tracks = self._paginate_items(collection, 'tracks')
            return tracks
        except Exception as e:
            logger.error(f"Error getting {expected_type} tracks: {e}")
            return []

    def _paginate_items(self, initial_data: dict, key: str = 'tracks') -> List[Dict[str, Any]]:
        items = []
        page = initial_data.get(key, {})

        while page.get('items'):
            if key == 'tracks' and 'track' in (page['items'][0] or {}):
                items.extend(item['track'] for item in page['items'] if item.get('track'))
            else:
                items.extend(page['items'])

            if page.get('next'):
                page = self.sp.next(page)
            else:
                break

        return items

    def get_playlist_tracks(self, playlist_uri: str) -> List[Dict[str, Any]]:
        tracks = self._get_tracks_from_collection(playlist_uri, 'playlist')
        if tracks:
            logger.info(f"Retrieved {len(tracks)} tracks from playlist")
        return tracks

    def get_album_tracks(self, album_uri: str) -> List[Dict[str, Any]]:
        tracks = self._get_tracks_from_collection(album_uri, 'album')
        if tracks:
            logger.info(f"Retrieved {len(tracks)} tracks from album")
        return tracks

    def track_to_youtube_query(self, track_info: Dict[str, Any]) -> str:
        title = track_info.get('name', '')
        artists = track_info.get('artists', [])
        artist = artists[0].get('name', '') if artists else ''

        if artist and title:
            return f"{artist} {title}"
        return title or artist
