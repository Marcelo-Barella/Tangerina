import pytest
from features.music.spotify_integration import SpotifyIntegration

@pytest.mark.unit
class TestSpotifyIntegrationParseUri:
    def setup_method(self):
        self.integration = SpotifyIntegration.__new__(SpotifyIntegration)
        self.integration.URI_PATTERN = SpotifyIntegration.URI_PATTERN
        self.integration.URL_PATTERN = SpotifyIntegration.URL_PATTERN

    def test_parse_uri_track_uri_format(self):
        result = self.integration.parse_uri('spotify:track:abc123')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_playlist_uri_format(self):
        result = self.integration.parse_uri('spotify:playlist:xyz789')
        assert result == {'type': 'playlist', 'id': 'xyz789'}

    def test_parse_uri_album_uri_format(self):
        result = self.integration.parse_uri('spotify:album:def456')
        assert result == {'type': 'album', 'id': 'def456'}

    def test_parse_uri_artist_uri_format(self):
        result = self.integration.parse_uri('spotify:artist:ghi789')
        assert result == {'type': 'artist', 'id': 'ghi789'}

    def test_parse_uri_track_url_format(self):
        result = self.integration.parse_uri('https://open.spotify.com/track/abc123')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_playlist_url_format(self):
        result = self.integration.parse_uri('https://open.spotify.com/playlist/xyz789')
        assert result == {'type': 'playlist', 'id': 'xyz789'}

    def test_parse_uri_album_url_format(self):
        result = self.integration.parse_uri('https://open.spotify.com/album/def456')
        assert result == {'type': 'album', 'id': 'def456'}

    def test_parse_uri_url_with_query_parameters(self):
        result = self.integration.parse_uri('https://open.spotify.com/track/abc123?si=xyz')
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_url_embedded_in_text(self):
        text = 'Check out this song: https://open.spotify.com/track/abc123 it\'s great!'
        result = self.integration.parse_uri(text)
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_uri_embedded_in_text(self):
        text = 'Play spotify:track:abc123 please'
        result = self.integration.parse_uri(text)
        assert result == {'type': 'track', 'id': 'abc123'}

    def test_parse_uri_invalid_format_returns_none(self):
        result = self.integration.parse_uri('not a spotify uri')
        assert result is None

    def test_parse_uri_empty_string_returns_none(self):
        result = self.integration.parse_uri('')
        assert result is None

    def test_parse_uri_youtube_url_returns_none(self):
        result = self.integration.parse_uri('https://youtube.com/watch?v=test123')
        assert result is None

    def test_parse_uri_alphanumeric_id(self):
        result = self.integration.parse_uri('spotify:track:1aB2cD3eF4')
        assert result == {'type': 'track', 'id': '1aB2cD3eF4'}

    def test_parse_uri_case_insensitive_type(self):
        result = self.integration.parse_uri('spotify:Track:abc123')
        assert result is None

    def test_parse_uri_url_without_protocol(self):
        result = self.integration.parse_uri('open.spotify.com/track/abc123')
        assert result == {'type': 'track', 'id': 'abc123'}


@pytest.mark.unit
class TestSpotifyIntegrationTrackToYoutubeQuery:
    def setup_method(self):
        self.integration = SpotifyIntegration.__new__(SpotifyIntegration)

    def test_track_to_youtube_query_with_artist_and_title(self):
        track = {
            'name': 'Bohemian Rhapsody',
            'artists': [{'name': 'Queen'}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Queen Bohemian Rhapsody'

    def test_track_to_youtube_query_with_multiple_artists(self):
        track = {
            'name': 'Old Town Road',
            'artists': [
                {'name': 'Lil Nas X'},
                {'name': 'Billy Ray Cyrus'}
            ]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Lil Nas X Old Town Road'

    def test_track_to_youtube_query_with_only_title(self):
        track = {
            'name': 'Unknown Track',
            'artists': []
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Unknown Track'

    def test_track_to_youtube_query_with_only_artist(self):
        track = {
            'name': '',
            'artists': [{'name': 'Queen'}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Queen'

    def test_track_to_youtube_query_with_missing_name_key(self):
        track = {
            'artists': [{'name': 'Queen'}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Queen'

    def test_track_to_youtube_query_with_missing_artists_key(self):
        track = {
            'name': 'Bohemian Rhapsody'
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Bohemian Rhapsody'

    def test_track_to_youtube_query_with_empty_artist_list(self):
        track = {
            'name': 'Test Song',
            'artists': []
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_empty_artist_name(self):
        track = {
            'name': 'Test Song',
            'artists': [{'name': ''}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_missing_artist_name_key(self):
        track = {
            'name': 'Test Song',
            'artists': [{}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Test Song'

    def test_track_to_youtube_query_with_all_empty(self):
        track = {
            'name': '',
            'artists': []
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == ''

    def test_track_to_youtube_query_with_special_characters(self):
        track = {
            'name': 'C\'est La Vie',
            'artists': [{'name': 'B*Witched'}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'B*Witched C\'est La Vie'

    def test_track_to_youtube_query_preserves_unicode(self):
        track = {
            'name': 'Despacito',
            'artists': [{'name': 'Luis Fonsi'}]
        }
        result = self.integration.track_to_youtube_query(track)
        assert result == 'Luis Fonsi Despacito'
