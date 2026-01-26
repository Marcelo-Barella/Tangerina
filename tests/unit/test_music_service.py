import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from tests.conftest import TEST_GUILD_ID, TEST_CHANNEL_ID, TEST_USER_ID
from tests.fixtures.discord_fixtures import (
    create_mock_guild,
    create_mock_voice_channel,
    create_mock_text_channel,
    create_mock_member,
    create_mock_voice_client
)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    return bot


@pytest.fixture
def mock_music_bot():
    music_bot = MagicMock()
    music_bot.voice_clients = {}
    music_bot.queues = {}
    music_bot.current_songs = {}
    music_bot.original_volumes = {}
    music_bot.voice_sinks = {}
    music_bot.ytdl = MagicMock()
    music_bot.main_loop = None
    music_bot.join_voice_channel = AsyncMock()
    music_bot.play_next = AsyncMock()
    music_bot._get_current_voice_channel = MagicMock(return_value=None)
    return music_bot


@pytest.fixture
def mock_spotify_client():
    client = MagicMock()
    client.parse_uri = MagicMock()
    client.get_track_info = MagicMock()
    client.get_playlist_tracks = MagicMock()
    client.get_album_tracks = MagicMock()
    return client


@pytest.fixture
def music_service(mock_bot, mock_music_bot, mock_spotify_client):
    from features.music.music_service import MusicService
    return MusicService(mock_bot, mock_music_bot, mock_spotify_client)


@pytest.fixture
def music_service_no_spotify(mock_bot, mock_music_bot):
    from features.music.music_service import MusicService
    return MusicService(mock_bot, mock_music_bot, None)


class TestGetUserVoiceChannel:
    @pytest.mark.asyncio
    async def test_guild_not_found(self, music_service, mock_bot):
        mock_bot.get_guild.return_value = None

        result = await music_service.get_user_voice_channel(TEST_GUILD_ID, TEST_USER_ID)

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_user_not_found(self, music_service, mock_bot):
        guild = create_mock_guild()
        guild.get_member = MagicMock(return_value=None)
        mock_bot.get_guild.return_value = guild

        result = await music_service.get_user_voice_channel(TEST_GUILD_ID, TEST_USER_ID)

        assert result['success'] is False
        assert 'user' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_user_not_in_voice(self, music_service, mock_bot):
        guild = create_mock_guild()
        member = create_mock_member()
        guild.get_member = MagicMock(return_value=member)
        mock_bot.get_guild.return_value = guild

        result = await music_service.get_user_voice_channel(TEST_GUILD_ID, TEST_USER_ID)

        assert result['success'] is True
        assert result['in_voice_channel'] is False
        assert result['channel_id'] is None

    @pytest.mark.asyncio
    async def test_user_in_voice_channel(self, music_service, mock_bot):
        guild = create_mock_guild()
        voice_channel = create_mock_voice_channel()
        member = create_mock_member(voice_channel=voice_channel)
        guild.get_member = MagicMock(return_value=member)
        mock_bot.get_guild.return_value = guild

        result = await music_service.get_user_voice_channel(TEST_GUILD_ID, TEST_USER_ID)

        assert result['success'] is True
        assert result['in_voice_channel'] is True
        assert result['channel_id'] == voice_channel.id
        assert result['channel_name'] == voice_channel.name


class TestPlaySpotifyMusic:
    @pytest.mark.asyncio
    async def test_no_spotify_client(self, music_service_no_spotify):
        result = await music_service_no_spotify.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:track:123"
        )

        assert result['success'] is False
        assert 'not configured' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_invalid_uri(self, music_service, mock_spotify_client):
        mock_spotify_client.parse_uri.return_value = None

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "invalid"
        )

        assert result['success'] is False
        assert 'invalid' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_track_uri(self, music_service, mock_spotify_client, mock_bot, mock_music_bot):
        import discord
        track = {'name': 'Test Song', 'artists': [{'name': 'Artist'}], 'id': '123'}
        mock_spotify_client.parse_uri.return_value = {'type': 'track'}
        mock_spotify_client.get_track_info.return_value = track

        guild = create_mock_guild()
        voice_channel = create_mock_voice_channel()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = False
        mock_music_bot.join_voice_channel.return_value = voice_client

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:track:123"
        )

        assert result['success'] is True
        assert result['tracks_queued'] == 1
        assert TEST_GUILD_ID in mock_music_bot.queues
        assert len(mock_music_bot.queues[TEST_GUILD_ID]) == 1

    @pytest.mark.asyncio
    async def test_playlist_uri(self, music_service, mock_spotify_client, mock_bot, mock_music_bot):
        import discord
        tracks = [
            {'name': 'Song 1', 'artists': [{'name': 'Artist 1'}]},
            {'name': 'Song 2', 'artists': [{'name': 'Artist 2'}]}
        ]
        mock_spotify_client.parse_uri.return_value = {'type': 'playlist'}
        mock_spotify_client.get_playlist_tracks.return_value = tracks

        guild = create_mock_guild()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = True
        mock_music_bot.join_voice_channel.return_value = voice_client

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:playlist:123"
        )

        assert result['success'] is True
        assert result['tracks_queued'] == 2

    @pytest.mark.asyncio
    async def test_album_uri(self, music_service, mock_spotify_client, mock_bot, mock_music_bot):
        import discord
        tracks = [{'name': 'Album Track', 'artists': [{'name': 'Artist'}]}]
        mock_spotify_client.parse_uri.return_value = {'type': 'album'}
        mock_spotify_client.get_album_tracks.return_value = tracks

        guild = create_mock_guild()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        mock_music_bot.join_voice_channel.return_value = voice_client

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:album:123"
        )

        assert result['success'] is True

    @pytest.mark.asyncio
    async def test_unsupported_type(self, music_service, mock_spotify_client):
        mock_spotify_client.parse_uri.return_value = {'type': 'artist'}

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:artist:123"
        )

        assert result['success'] is False
        assert 'unsupported' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_no_tracks_found(self, music_service, mock_spotify_client):
        mock_spotify_client.parse_uri.return_value = {'type': 'track'}
        mock_spotify_client.get_track_info.return_value = None

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:track:123"
        )

        assert result['success'] is False
        assert 'no tracks' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_guild_not_found(self, music_service, mock_spotify_client, mock_bot):
        mock_spotify_client.parse_uri.return_value = {'type': 'track'}
        mock_spotify_client.get_track_info.return_value = {'name': 'Song', 'artists': []}
        mock_bot.get_guild.return_value = None

        result = await music_service.play_spotify_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "spotify:track:123"
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()


class TestPlayMusic:
    @pytest.mark.asyncio
    async def test_spotify_url_redirect(self, music_service, mock_spotify_client):
        mock_spotify_client.parse_uri.return_value = {'type': 'track'}
        mock_spotify_client.get_track_info.return_value = None

        result = await music_service.play_music(
            TEST_GUILD_ID, TEST_CHANNEL_ID, "https://open.spotify.com/track/123"
        )

        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_youtube_search(self, music_service_no_spotify, mock_bot, mock_music_bot):
        import discord
        guild = create_mock_guild()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = False
        mock_music_bot.join_voice_channel.return_value = voice_client

        song_data = {
            'title': 'Test Video',
            'url': 'https://youtube.com/watch?v=123',
            'duration': 240
        }

        with patch('features.music.music_service.YTDLSource') as mock_ytdl:
            mock_ytdl.search_youtube = AsyncMock(return_value=song_data)
            mock_ytdl.from_url = AsyncMock(return_value=MagicMock())

            result = await music_service_no_spotify.play_music(
                TEST_GUILD_ID, TEST_CHANNEL_ID, "test query"
            )

        assert result['success'] is True
        assert result['song']['title'] == 'Test Video'
        assert result['queued'] is False

    @pytest.mark.asyncio
    async def test_youtube_no_results(self, music_service_no_spotify, mock_bot, mock_music_bot):
        import discord
        guild = create_mock_guild()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        mock_music_bot.join_voice_channel.return_value = voice_client

        with patch('features.music.music_service.YTDLSource') as mock_ytdl:
            mock_ytdl.search_youtube = AsyncMock(return_value=None)

            result = await music_service_no_spotify.play_music(
                TEST_GUILD_ID, TEST_CHANNEL_ID, "test query"
            )

        assert result['success'] is False
        assert 'no results' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_queue_when_playing(self, music_service_no_spotify, mock_bot, mock_music_bot):
        import discord
        guild = create_mock_guild()
        voice_channel_instance = MagicMock(spec=discord.VoiceChannel)
        voice_channel_instance.id = TEST_CHANNEL_ID
        guild.get_channel.return_value = voice_channel_instance
        mock_bot.get_guild.return_value = guild

        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = True
        mock_music_bot.join_voice_channel.return_value = voice_client

        song_data = {'title': 'Test Video', 'url': 'https://youtube.com/watch?v=123'}

        with patch('features.music.music_service.YTDLSource') as mock_ytdl:
            mock_ytdl.search_youtube = AsyncMock(return_value=song_data)

            result = await music_service_no_spotify.play_music(
                TEST_GUILD_ID, TEST_CHANNEL_ID, "test query"
            )

        assert result['success'] is True
        assert result['queued'] is True
        assert TEST_GUILD_ID in mock_music_bot.queues

    @pytest.mark.asyncio
    async def test_text_channel_with_bot_in_voice(self, music_service_no_spotify, mock_bot, mock_music_bot):
        guild = create_mock_guild()
        text_channel = create_mock_text_channel()
        voice_channel = create_mock_voice_channel()

        guild.get_channel.return_value = text_channel
        mock_bot.get_guild.return_value = guild

        current_vc = MagicMock()
        current_vc.channel = voice_channel
        mock_music_bot._get_current_voice_channel.return_value = current_vc

        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = False
        mock_music_bot.join_voice_channel.return_value = voice_client

        song_data = {'title': 'Test', 'url': 'https://youtube.com/watch?v=123'}

        with patch('features.music.music_service.YTDLSource') as mock_ytdl:
            mock_ytdl.search_youtube = AsyncMock(return_value=song_data)
            mock_ytdl.from_url = AsyncMock(return_value=MagicMock())

            result = await music_service_no_spotify.play_music(
                TEST_GUILD_ID, text_channel.id, "test"
            )

        assert result['success'] is True


class TestStopMusic:
    @pytest.mark.asyncio
    async def test_not_in_voice(self, music_service, mock_music_bot):
        result = await music_service.stop_music(TEST_GUILD_ID)

        assert result['success'] is False
        assert 'not in voice' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_stop_success(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client
        mock_music_bot.queues[TEST_GUILD_ID] = [{'title': 'Song'}]

        result = await music_service.stop_music(TEST_GUILD_ID)

        assert result['success'] is True
        voice_client.stop.assert_called_once()
        assert mock_music_bot.queues[TEST_GUILD_ID] == []


class TestSkipMusic:
    @pytest.mark.asyncio
    async def test_no_music_playing(self, music_service, mock_music_bot):
        result = await music_service.skip_music(TEST_GUILD_ID)

        assert result['success'] is False
        assert 'no music' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_skip_success(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = True
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.skip_music(TEST_GUILD_ID)

        assert result['success'] is True
        voice_client.stop.assert_called_once()


class TestPauseMusic:
    @pytest.mark.asyncio
    async def test_no_music_playing(self, music_service, mock_music_bot):
        result = await music_service.pause_music(TEST_GUILD_ID)

        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_pause_success(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        voice_client.is_playing.return_value = True
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.pause_music(TEST_GUILD_ID)

        assert result['success'] is True
        voice_client.pause.assert_called_once()


class TestResumeMusic:
    @pytest.mark.asyncio
    async def test_music_not_paused(self, music_service, mock_music_bot):
        result = await music_service.resume_music(TEST_GUILD_ID)

        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_resume_success(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        voice_client.is_paused = MagicMock(return_value=True)
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.resume_music(TEST_GUILD_ID)

        assert result['success'] is True
        voice_client.resume.assert_called_once()


class TestSetVolume:
    @pytest.mark.asyncio
    async def test_not_in_voice(self, music_service, mock_music_bot):
        result = await music_service.set_volume(TEST_GUILD_ID, 50)

        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_set_volume_success(self, music_service, mock_music_bot):
        import discord
        voice_client = create_mock_voice_client()
        source = MagicMock(spec=discord.PCMVolumeTransformer)
        voice_client.source = source
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.set_volume(TEST_GUILD_ID, 75)

        assert result['success'] is True
        assert result['volume'] == 75
        assert source.volume == 0.75

    @pytest.mark.asyncio
    async def test_set_volume_no_source(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        voice_client.source = None
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.set_volume(TEST_GUILD_ID, 50)

        assert result['success'] is False


class TestGetQueue:
    @pytest.mark.asyncio
    async def test_empty_queue(self, music_service, mock_music_bot):
        result = await music_service.get_queue(TEST_GUILD_ID)

        assert result['queue'] == []
        assert result['current'] is None
        assert result['total'] == 0

    @pytest.mark.asyncio
    async def test_queue_with_items(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': 'Song 1', 'url': 'url1'},
            {'title': 'Song 2', 'url': 'url2'}
        ]
        mock_music_bot.current_songs[TEST_GUILD_ID] = {'title': 'Current Song'}

        result = await music_service.get_queue(TEST_GUILD_ID)

        assert len(result['queue']) == 2
        assert result['current']['title'] == 'Current Song'
        assert result['total'] == 2

    @pytest.mark.asyncio
    async def test_queue_with_limit(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': f'Song {i}'} for i in range(10)
        ]

        result = await music_service.get_queue(TEST_GUILD_ID, limit=3)

        assert len(result['queue']) == 3
        assert result['total'] == 10

    @pytest.mark.asyncio
    async def test_queue_with_offset(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': f'Song {i}'} for i in range(10)
        ]

        result = await music_service.get_queue(TEST_GUILD_ID, offset=5, limit=3)

        assert len(result['queue']) == 3
        assert result['queue'][0]['title'] == 'Song 5'

    @pytest.mark.asyncio
    async def test_queue_minimal_info(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': 'Song 1', 'url': 'url1', 'duration': 240}
        ]

        result = await music_service.get_queue(TEST_GUILD_ID, info_level='minimal')

        assert 'title' in result['queue'][0]
        assert 'position' in result['queue'][0]
        assert 'url' not in result['queue'][0]

    @pytest.mark.asyncio
    async def test_queue_name_only(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': 'Song 1', 'url': 'url1'}
        ]

        result = await music_service.get_queue(TEST_GUILD_ID, info_level='name')

        assert result['queue'][0] == {'title': 'Song 1'}

    @pytest.mark.asyncio
    async def test_queue_link_info(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [
            {'title': 'Song 1', 'url': 'url1'}
        ]

        result = await music_service.get_queue(TEST_GUILD_ID, info_level='link')

        assert 'title' in result['queue'][0]
        assert 'url' in result['queue'][0]
        assert 'duration' not in result['queue'][0]

    @pytest.mark.asyncio
    async def test_queue_exclude_current(self, music_service, mock_music_bot):
        mock_music_bot.current_songs[TEST_GUILD_ID] = {'title': 'Current'}

        result = await music_service.get_queue(TEST_GUILD_ID, include_current=False)

        assert result['current'] is None

    @pytest.mark.asyncio
    async def test_queue_limit_zero(self, music_service, mock_music_bot):
        mock_music_bot.queues[TEST_GUILD_ID] = [{'title': 'Song'}]

        result = await music_service.get_queue(TEST_GUILD_ID, limit=0)

        assert result['queue'] == []
        assert result['total'] == 1


class TestLeaveMusic:
    @pytest.mark.asyncio
    async def test_not_in_voice(self, music_service, mock_music_bot):
        result = await music_service.leave_music(TEST_GUILD_ID)

        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_leave_success(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        voice_sink = MagicMock()
        voice_sink.cleanup = MagicMock()

        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client
        mock_music_bot.queues[TEST_GUILD_ID] = []
        mock_music_bot.current_songs[TEST_GUILD_ID] = {}
        mock_music_bot.original_volumes[TEST_GUILD_ID] = 0.5
        mock_music_bot.voice_sinks[TEST_GUILD_ID] = voice_sink

        result = await music_service.leave_music(TEST_GUILD_ID)

        assert result['success'] is True
        voice_client.disconnect.assert_called_once()
        voice_sink.cleanup.assert_called_once()
        assert TEST_GUILD_ID not in mock_music_bot.voice_clients
        assert TEST_GUILD_ID not in mock_music_bot.queues
        assert TEST_GUILD_ID not in mock_music_bot.current_songs

    @pytest.mark.asyncio
    async def test_leave_without_sink(self, music_service, mock_music_bot):
        voice_client = create_mock_voice_client()
        mock_music_bot.voice_clients[TEST_GUILD_ID] = voice_client

        result = await music_service.leave_music(TEST_GUILD_ID)

        assert result['success'] is True
