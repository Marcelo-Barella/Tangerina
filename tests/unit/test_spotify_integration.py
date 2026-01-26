import pytest
from unittest.mock import MagicMock, patch
from features.music.spotify_integration import SpotifyIntegration

@pytest.fixture
def spotify_integration():
    integration = SpotifyIntegration.__new__(SpotifyIntegration)
    integration.URI_PATTERN = SpotifyIntegration.URI_PATTERN
    integration.URL_PATTERN = SpotifyIntegration.URL_PATTERN
    return integration

@pytest.mark.unit
class TestSpotifyIntegrationParseUri:

    def test_parse_uri_track_uri_format(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:track:abc123')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_playlist_uri_format(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:playlist:xyz789')
        assert result == {'type': 'playlist', 'id': 'xyz789'}

    def test_parse_uri_album_uri_format(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:album:def456')
        assert result == {'type': 'album', 'id': 'def456'}

    def test_parse_uri_artist_uri_format(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:artist:ghi789')
        assert result == {'type': 'artist', 'id': 'ghi789'}

    def test_parse_uri_track_url_format(self, spotify_integration):
        result = spotify_integration.parse_uri('https://open.spotify.com/track/abc123')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_playlist_url_format(self, spotify_integration):
        result = spotify_integration.parse_uri('https://open.spotify.com/playlist/xyz789')
        assert result == {'type': 'playlist', 'id': 'xyz789'}

    def test_parse_uri_album_url_format(self, spotify_integration):
        result = spotify_integration.parse_uri('https://open.spotify.com/album/def456')
        assert result == {'type': 'album', 'id': 'def456'}

    def test_parse_uri_url_with_query_parameters(self, spotify_integration):
        result = spotify_integration.parse_uri('https://open.spotify.com/track/abc123?si=xyz')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_url_embedded_in_text(self, spotify_integration):
        text = 'Check out this song: https://open.spotify.com/track/abc123 it\'s great!'
        result = spotify_integration.parse_uri(text)
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_uri_embedded_in_text(self, spotify_integration):
        text = 'Play spotify:track:abc123 please'
        result = spotify_integration.parse_uri(text)
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_invalid_format_returns_none(self, spotify_integration):
        result = spotify_integration.parse_uri('not a spotify uri')
        assert result is None

    def test_parse_uri_empty_string_returns_none(self, spotify_integration):
        result = spotify_integration.parse_uri('')
        assert result is None

    def test_parse_uri_youtube_url_returns_none(self, spotify_integration):
        result = spotify_integration.parse_uri('https://youtube.com/watch?v=test123')
        assert result is None

    def test_parse_uri_alphanumeric_id(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:track:1aB2cD3eF4')
        assert result == {'type': 'track', 'id': '1aB2cD3eF4'}

    def test_parse_uri_type_case_sensitive(self, spotify_integration):
        result = spotify_integration.parse_uri('spotify:Track:abc123')
        assert result is None

    def test_parse_uri_url_without_protocol(self, spotify_integration):
        result = spotify_integration.parse_uri('open.spotify.com/track/abc123')
        assert result == {'type': 'track', 'id': 'abc123'}


@pytest.mark.unit
class TestSpotifyIntegrationTrackToYoutubeQuery:
    def test_track_to_youtube_query_with_artist_and_title(self, spotify_integration):
        track = {
            'name': 'Bohemian Rhapsody',
            'artists': [{'name': 'Queen'}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Queen Bohemian Rhapsody'

    def test_track_to_youtube_query_with_multiple_artists(self, spotify_integration):
        track = {
            'name': 'Old Town Road',
            'artists': [
                {'name': 'Lil Nas X'},
                {'name': 'Billy Ray Cyrus'}
            ]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Lil Nas X Old Town Road'

    def test_track_to_youtube_query_with_only_title(self, spotify_integration):
        track = {
            'name': 'Unknown Track',
            'artists': []
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Unknown Track'

    def test_track_to_youtube_query_with_only_artist(self, spotify_integration):
        track = {
            'name': '',
            'artists': [{'name': 'Queen'}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Queen'

    def test_track_to_youtube_query_with_missing_name_key(self, spotify_integration):
        track = {
            'artists': [{'name': 'Queen'}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Queen'

    def test_track_to_youtube_query_with_missing_artists_key(self, spotify_integration):
        track = {
            'name': 'Bohemian Rhapsody'
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Bohemian Rhapsody'

    def test_track_to_youtube_query_with_empty_artist_list(self, spotify_integration):
        track = {
            'name': 'Test Song',
            'artists': []
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_empty_artist_name(self, spotify_integration):
        track = {
            'name': 'Test Song',
            'artists': [{'name': ''}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_missing_artist_name_key(self, spotify_integration):
        track = {
            'name': 'Test Song',
            'artists': [{}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_all_empty(self, spotify_integration):
        track = {
            'name': '',
            'artists': []
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == ''

    def test_track_to_youtube_query_with_special_characters(self, spotify_integration):
        track = {
            'name': 'C\'est La Vie',
            'artists': [{'name': 'B*Witched'}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'B*Witched C\'est La Vie'

    def test_track_to_youtube_query_preserves_unicode(self, spotify_integration):
        track = {
            'name': 'Despacito',
            'artists': [{'name': 'Luis Fonsi'}]
        }
        result = spotify_integration.track_to_youtube_query(track)
        assert result == 'Luis Fonsi Despacito'


@pytest.mark.unit
class TestSpotifyIntegrationInit:
    @patch('features.music.spotify_integration.spotipy.Spotify')
    @patch('features.music.spotify_integration.SpotifyClientCredentials')
    def test_init_creates_spotify_client(self, mock_creds, mock_spotify):
        integration = SpotifyIntegration('client_id', 'client_secret')

        mock_creds.assert_called_once_with(client_id='client_id', client_secret='client_secret')
        mock_spotify.assert_called_once()
        assert integration.sp is not None


@pytest.mark.unit
class TestSpotifyIntegrationGetTrackInfo:
    def test_get_track_info_success(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        track_data = {'name': 'Test Track', 'id': 'abc123'}
        spotify_integration.sp.track.return_value = track_data

        result = spotify_integration.get_track_info('spotify:track:abc123')

        assert result == track_data
        spotify_integration.sp.track.assert_called_once_with('abc123')

    def test_get_track_info_invalid_uri(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration.get_track_info('invalid')

        assert result is None
        spotify_integration.sp.track.assert_not_called()

    def test_get_track_info_wrong_type(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration.get_track_info('spotify:playlist:abc123')

        assert result is None
        spotify_integration.sp.track.assert_not_called()

    def test_get_track_info_api_error(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        spotify_integration.sp.track.side_effect = Exception('API Error')

        result = spotify_integration.get_track_info('spotify:track:abc123')

        assert result is None


@pytest.mark.unit
class TestSpotifyIntegrationGetTracksFromCollection:
    def test_get_playlist_tracks_success(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        playlist_data = {
            'tracks': {
                'items': [
                    {'track': {'name': 'Track 1', 'id': '1'}},
                    {'track': {'name': 'Track 2', 'id': '2'}}
                ],
                'next': None
            }
        }
        spotify_integration.sp.playlist.return_value = playlist_data

        result = spotify_integration.get_playlist_tracks('spotify:playlist:abc123')

        assert len(result) == 2
        assert result[0]['name'] == 'Track 1'
        assert result[1]['name'] == 'Track 2'

    def test_get_playlist_tracks_invalid_uri(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration.get_playlist_tracks('invalid')

        assert result == []
        spotify_integration.sp.playlist.assert_not_called()

    def test_get_playlist_tracks_wrong_type(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration.get_playlist_tracks('spotify:track:abc123')

        assert result == []
        spotify_integration.sp.playlist.assert_not_called()

    def test_get_playlist_tracks_api_error(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        spotify_integration.sp.playlist.side_effect = Exception('API Error')

        result = spotify_integration.get_playlist_tracks('spotify:playlist:abc123')

        assert result == []

    def test_get_album_tracks_success(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        album_data = {
            'tracks': {
                'items': [
                    {'name': 'Track 1', 'id': '1'},
                    {'name': 'Track 2', 'id': '2'}
                ],
                'next': None
            }
        }
        spotify_integration.sp.album.return_value = album_data

        result = spotify_integration.get_album_tracks('spotify:album:abc123')

        assert len(result) == 2
        assert result[0]['name'] == 'Track 1'

    def test_get_album_tracks_invalid_uri(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration.get_album_tracks('invalid')

        assert result == []

    def test_get_album_tracks_api_error(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        spotify_integration.sp.album.side_effect = Exception('API Error')

        result = spotify_integration.get_album_tracks('spotify:album:abc123')

        assert result == []

    def test_get_tracks_from_collection_empty_result(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        spotify_integration.sp.playlist.return_value = None

        result = spotify_integration.get_playlist_tracks('spotify:playlist:abc123')

        assert result == []

    def test_get_tracks_from_collection_unsupported_type(self, spotify_integration):
        spotify_integration.sp = MagicMock()

        result = spotify_integration._get_tracks_from_collection('spotify:artist:abc123', 'artist')

        assert result == []


@pytest.mark.unit
class TestSpotifyIntegrationPagination:
    def test_paginate_items_single_page(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        initial_data = {
            'tracks': {
                'items': [
                    {'track': {'name': 'Track 1'}},
                    {'track': {'name': 'Track 2'}}
                ],
                'next': None
            }
        }

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert len(result) == 2
        assert result[0]['name'] == 'Track 1'

    def test_paginate_items_multiple_pages(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        page1 = {
            'items': [
                {'track': {'name': 'Track 1'}},
                {'track': {'name': 'Track 2'}}
            ],
            'next': 'page2_url'
        }
        page2 = {
            'items': [
                {'track': {'name': 'Track 3'}}
            ],
            'next': None
        }

        initial_data = {'tracks': page1}
        spotify_integration.sp.next.return_value = page2

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert len(result) == 3
        assert result[2]['name'] == 'Track 3'
        spotify_integration.sp.next.assert_called_once()

    def test_paginate_items_album_format(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        initial_data = {
            'tracks': {
                'items': [
                    {'name': 'Track 1'},
                    {'name': 'Track 2'}
                ],
                'next': None
            }
        }

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert len(result) == 2
        assert result[0]['name'] == 'Track 1'

    def test_paginate_items_skip_null_tracks(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        initial_data = {
            'tracks': {
                'items': [
                    {'track': {'name': 'Track 1'}},
                    {'track': None},
                    {'track': {'name': 'Track 2'}}
                ],
                'next': None
            }
        }

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert len(result) == 2
        assert result[0]['name'] == 'Track 1'
        assert result[1]['name'] == 'Track 2'

    def test_paginate_items_empty_items(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        initial_data = {
            'tracks': {
                'items': [],
                'next': None
            }
        }

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert result == []

    def test_paginate_items_no_tracks_key(self, spotify_integration):
        spotify_integration.sp = MagicMock()
        initial_data = {}

        result = spotify_integration._paginate_items(initial_data, 'tracks')

        assert result == []
