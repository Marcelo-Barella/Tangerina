import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from features.voice.voice_commands import (
    WAKE_WORD,
    CANCEL_KEYWORDS,
    VOLUME_MIN,
    VOLUME_MAX,
    LISTENING_DURATION,
    WHISPER_INITIAL_PROMPT,
    VoiceCommandSink,
)
from tests.conftest import TEST_GUILD_ID

SPEECH_PCM_CHUNK = b'\xff\x7f' * 1920


def _fill_speech_buffer(sink, user_id, chunk_count=20):
    from collections import deque
    sink.audio_buffers[user_id] = deque(maxlen=150)
    for _ in range(chunk_count):
        sink.audio_buffers[user_id].append(SPEECH_PCM_CHUNK)

@pytest.mark.unit
class TestVoiceCommandConstants:
    def test_wake_word_is_tangerina(self):
        assert WAKE_WORD == 'tangerina'

    def test_volume_min_is_zero(self):
        assert VOLUME_MIN == 0

    def test_volume_max_is_hundred(self):
        assert VOLUME_MAX == 100

    def test_listening_duration_is_positive(self):
        assert LISTENING_DURATION > 0
        assert isinstance(LISTENING_DURATION, float)

    def test_cancel_keywords_contains_cancel_variants(self):
        assert 'cancel' in CANCEL_KEYWORDS
        assert 'cancelar' in CANCEL_KEYWORDS
        assert 'stop' in CANCEL_KEYWORDS
        assert 'parar' in CANCEL_KEYWORDS

    def test_cancel_keywords_is_list(self):
        assert isinstance(CANCEL_KEYWORDS, list)
        assert len(CANCEL_KEYWORDS) > 0


@pytest.fixture
def sink_instance():
    mock_bot = MagicMock()
    mock_vc = MagicMock()
    mock_music_service = MagicMock()
    return VoiceCommandSink(
        bot_instance=mock_bot,
        voice_client=mock_vc,
        guild_id=TEST_GUILD_ID,
        zhipu_api_key=None,
        whisper_provider='sidecar',
        music_service=mock_music_service
    ), mock_bot, mock_vc, mock_music_service


@pytest.mark.unit
class TestVoiceCommandSinkInit:
    def test_voice_command_sink_initialization(self, sink_instance):
        sink, mock_bot, mock_vc, _ = sink_instance
        
        assert sink.bot == mock_bot
        assert sink._voice_client == mock_vc
        assert sink.guild_id == TEST_GUILD_ID
        assert sink.whisper_provider == 'sidecar'
        assert isinstance(sink.audio_buffers, dict)
        assert isinstance(sink.speaking_users, set)

    def test_voice_command_sink_voice_commands_mapping(self):
        assert VoiceCommandSink.VOICE_COMMANDS['play'] == ['toca', 'play', 'tocar']
        assert VoiceCommandSink.VOICE_COMMANDS['stop'] == ['para', 'stop', 'parar']
        assert VoiceCommandSink.VOICE_COMMANDS['skip'] == ['pula', 'skip', 'pular']
        assert VoiceCommandSink.VOICE_COMMANDS['pause'] == ['pausa', 'pause', 'pausar']
        assert VoiceCommandSink.VOICE_COMMANDS['resume'] == ['continua', 'resume', 'continuar']


@pytest.mark.unit
class TestVoiceCommandSinkAudioProcessing:
    def test_write_adds_audio_buffer(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'audio_data'
        
        sink.write(mock_user, mock_audio_data)
        
        assert mock_user.id in sink.audio_buffers
        assert len(sink.audio_buffers[mock_user.id]) == 1

    def test_write_ignores_none_user(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink.write(None, MagicMock())
        assert len(sink.audio_buffers) == 0

    def test_write_ignores_audio_without_pcm(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = None
        mock_audio_data.opus = None
        
        sink.write(mock_user, mock_audio_data)
        assert mock_user.id not in sink.audio_buffers

    def test_wants_opus_returns_false(self, sink_instance):
        sink, _, _, _ = sink_instance
        assert sink.wants_opus() is False

    def test_write_buffers_voice_recv_pcm(self, sink_instance):
        sink, _, _, _ = sink_instance
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'pcm-bytes'
        mock_audio_data.opus = b'opus-frame'

        sink.write(mock_user, mock_audio_data)

        assert len(sink.audio_buffers[999]) == 1

    def test_write_skips_failed_voice_recv_pcm(self, sink_instance):
        sink, _, _, _ = sink_instance
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b''
        mock_audio_data.opus = b'opus-frame'

        sink.write(mock_user, mock_audio_data)

        assert mock_user.id not in sink.audio_buffers

    def test_write_skips_opus_silence_packet(self, sink_instance):
        sink, _, _, _ = sink_instance
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'pcm-bytes'
        mock_audio_data.packet = MagicMock()
        mock_audio_data.packet.decrypted_data = b'\xf8\xff\xfe'

        sink.write(mock_user, mock_audio_data)

        assert mock_user.id not in sink.audio_buffers

    def test_write_ignores_empty_pcm(self, sink_instance):
        sink, _, _, _ = sink_instance
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b''
        mock_audio_data.opus = None

        sink.write(mock_user, mock_audio_data)
        assert mock_user.id not in sink.audio_buffers

    def test_has_speech_energy_rejects_quiet_audio(self, sink_instance):
        sink, _, _, _ = sink_instance
        assert sink._has_speech_energy(b'\x00\x00' * 100) is False
        assert sink._has_speech_energy(SPEECH_PCM_CHUNK) is True


@pytest.mark.unit
class TestVoiceCommandSinkSpeechRouting:
    @pytest.mark.asyncio
    async def test_route_speech_with_wake_word(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._handle_voice_command = AsyncMock()
        
        mock_member = MagicMock(spec=discord.Member)
        await sink._route_speech(mock_member, "tangerina toca música")
        
        sink._handle_voice_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_speech_activates_listening_mode(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._activate_listening_mode = AsyncMock()
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        
        await sink._route_speech(mock_member, "tangerina")
        sink._activate_listening_mode.assert_called_once_with(mock_member)

    @pytest.mark.asyncio
    async def test_route_speech_in_listening_mode_handles_listening(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._handle_listening_mode = AsyncMock()
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        sink.listening_mode[999] = True
        
        await sink._route_speech(mock_member, "tangerina hello world")
        sink._handle_listening_mode.assert_called_once()


@pytest.mark.unit
class TestVoiceCommandSinkHandlePlay:
    @pytest.mark.asyncio
    async def test_handle_play_extracts_query(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.play_music = AsyncMock(return_value={'message': 'Playing...'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_play(mock_channel, "toca bohemian rhapsody")
        
        mock_music_service.play_music.assert_called_once()
        args = mock_music_service.play_music.call_args[0]
        assert 'bohemian rhapsody' in args[2].lower()

    @pytest.mark.asyncio
    async def test_handle_play_ignores_empty_query(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_channel = MagicMock(spec=discord.TextChannel)
        
        await sink._handle_play(mock_channel, "toca")
        mock_music_service.play_music.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_volume_validates_range(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_channel = MagicMock(spec=discord.TextChannel)
        
        await sink._handle_volume(mock_channel, "volume 150")
        mock_music_service.set_volume.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_volume_accepts_valid_volume(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.set_volume = AsyncMock(return_value={'message': 'Volume set'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_volume(mock_channel, "volume 50")
        mock_music_service.set_volume.assert_called_once()


@pytest.mark.unit
class TestVoiceCommandSinkListeningMode:
    @pytest.mark.asyncio
    async def test_activate_listening_mode_lowers_volume(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.set_volume = AsyncMock(return_value={'message': 'Volume set'})
        sink._get_current_volume = AsyncMock(return_value=100.0)
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"
        
        await sink._activate_listening_mode(mock_member)
        
        assert sink.listening_mode[999] is True
        assert sink.original_volumes[999] == 100.0
        mock_music_service.set_volume.assert_called()

    @pytest.mark.asyncio
    async def test_deactivate_listening_mode_restores_volume(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.set_volume = AsyncMock(return_value={'message': 'Volume set'})
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"
        
        sink.listening_mode[999] = True
        sink.original_volumes[999] = 80.0
        
        await sink._deactivate_listening_mode(mock_member)
        
        assert sink.listening_mode[999] is False
        mock_music_service.set_volume.assert_called_with(TEST_GUILD_ID, 80)

    @pytest.mark.asyncio
    async def test_handle_listening_mode_cancel_keywords(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._deactivate_listening_mode = AsyncMock()
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        
        await sink._handle_listening_mode(mock_member, "cancel")
        sink._deactivate_listening_mode.assert_called_once()


@pytest.mark.unit
class TestVoiceCommandSinkTranscription:
    @pytest.mark.asyncio
    async def test_process_speech_requires_minimum_chunks(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._transcribe_audio = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999

        from collections import deque
        sink.audio_buffers[999] = deque(maxlen=150)
        sink.audio_buffers[999].append(b'chunk1')
        await sink.process_speech(mock_member)
        
        sink._transcribe_audio.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_speech_skips_insufficient_pcm_bytes(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._transcribe_audio = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999

        from collections import deque
        sink.audio_buffers[999] = deque([b'x' * 100] * 15, maxlen=150)

        await sink.process_speech(mock_member)

        sink._transcribe_audio.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_speech_clears_buffer(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(return_value="toca música")
        sink._route_speech = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"

        from collections import deque
        sink.audio_buffers[999] = deque(maxlen=150)
        for _ in range(15):
            sink.audio_buffers[999].append(b'chunk')
        
        await sink.process_speech(mock_member)
        assert len(sink.audio_buffers[999]) == 0


@pytest.mark.unit
class TestVoiceCommandSinkCleanup:
    def test_cleanup_clears_buffers(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        sink.audio_buffers[999] = MagicMock()
        sink.speaking_users.add(999)
        sink.listening_mode[999] = True
        
        sink.cleanup()
        
        assert len(sink.audio_buffers) == 0
        assert len(sink.speaking_users) == 0
        assert len(sink.listening_mode) == 0


@pytest.mark.unit
class TestVoiceCommandSinkAudioCombining:
    def test_combine_audio_chunks_returns_wav_buffer(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        import io
        result = sink._combine_audio_chunks([b'chunk1', b'chunk2'])
        
        assert isinstance(result, io.BytesIO)
        result.seek(0)
        content = result.read(4)
        assert content == b'RIFF'

    def test_combine_audio_chunks_creates_mono_audio(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        import io
        import wave
        chunks = [b'\x00\x01' * 100]
        result = sink._combine_audio_chunks(chunks)
        
        result.seek(0)
        with wave.open(result, 'rb') as wav_file:
            assert wav_file.getnchannels() == 1


@pytest.mark.unit
class TestVoiceCommandSinkCommandHandlers:
    @pytest.mark.asyncio
    async def test_handle_stop_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.stop_music = AsyncMock(return_value={'message': 'Stopped'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_stop(mock_channel, "para")
        mock_music_service.stop_music.assert_called_once_with(TEST_GUILD_ID)

    @pytest.mark.asyncio
    async def test_handle_skip_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.skip_music = AsyncMock(return_value={'message': 'Skipped'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_skip(mock_channel, "pula")
        mock_music_service.skip_music.assert_called_once_with(TEST_GUILD_ID)

    @pytest.mark.asyncio
    async def test_handle_pause_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.pause_music = AsyncMock(return_value={'message': 'Paused'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_pause(mock_channel, "pausa")
        mock_music_service.pause_music.assert_called_once_with(TEST_GUILD_ID)

    @pytest.mark.asyncio
    async def test_handle_resume_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.resume_music = AsyncMock(return_value={'message': 'Resumed'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_resume(mock_channel, "continua")
        mock_music_service.resume_music.assert_called_once_with(TEST_GUILD_ID)

    @pytest.mark.asyncio
    async def test_handle_queue_displays_queue(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.get_queue = AsyncMock(return_value={
            'queue': [
                {'title': 'Song1'},
                {'title': 'Song2'},
                {'title': 'Song3'}
            ]
        })
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_queue(mock_channel, "fila")
        
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert 'Song1' in call_args

    @pytest.mark.asyncio
    async def test_handle_queue_shows_empty_message(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.get_queue = AsyncMock(return_value={'queue': []})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_queue(mock_channel, "fila")
        
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args[0][0]
        assert 'vazia' in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_leave_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.leave_music = AsyncMock(return_value={'message': 'Left'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_leave(mock_channel, "sai")
        mock_music_service.leave_music.assert_called_once_with(TEST_GUILD_ID)


@pytest.mark.unit
class TestVoiceCommandSinkHandleVoiceCommand:
    @pytest.mark.asyncio
    async def test_handle_voice_command_routes_play_command(self, sink_instance):
        sink, mock_bot, _, _ = sink_instance
        sink._handle_play = AsyncMock()
        
        mock_guild = MagicMock()
        mock_text_channel = MagicMock(spec=discord.TextChannel)
        mock_text_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
        mock_guild.text_channels = [mock_text_channel]
        mock_bot.get_guild.return_value = mock_guild
        
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        
        await sink._handle_voice_command(mock_member, "toca music")
        sink._handle_play.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_voice_command_routes_stop_command(self, sink_instance):
        sink, mock_bot, _, _ = sink_instance
        sink._handle_stop = AsyncMock()
        
        mock_guild = MagicMock()
        mock_text_channel = MagicMock(spec=discord.TextChannel)
        mock_text_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
        mock_guild.text_channels = [mock_text_channel]
        mock_bot.get_guild.return_value = mock_guild
        
        mock_member = MagicMock(spec=discord.Member)
        
        await sink._handle_voice_command(mock_member, "para")
        sink._handle_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_voice_command_volume_no_text_channel(self, sink_instance):
        sink, mock_bot, _, _ = sink_instance
        mock_bot.get_guild.return_value = None
        
        mock_member = MagicMock(spec=discord.Member)
        await sink._handle_voice_command(mock_member, "volume 50")


@pytest.mark.unit
class TestVoiceCommandSinkTranscriptionProviders:
    @pytest.mark.asyncio
    async def test_transcribe_audio_routes_to_sidecar(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._transcribe_sidecar = AsyncMock(return_value="toca música")
        
        import io
        audio_data = io.BytesIO(b'test')
        result = await sink._transcribe_audio(audio_data)
        
        assert result == "toca música"
        sink._transcribe_sidecar.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_audio_routes_to_zhipu(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()
        
        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=TEST_GUILD_ID,
            zhipu_api_key='test_key',
            whisper_provider='zhipu',
            music_service=mock_music_service
        )
        
        sink._transcribe_zhipu = AsyncMock(return_value="toca música")
        
        import io
        audio_data = io.BytesIO(b'test')
        result = await sink._transcribe_audio(audio_data)
        
        assert result == "toca música"
        sink._transcribe_zhipu.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_audio_routes_to_openai_api(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()

        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=TEST_GUILD_ID,
            zhipu_api_key=None,
            whisper_provider='openai-api',
            music_service=mock_music_service,
            openai_api_key='test_openai_key',
        )

        sink._transcribe_openai_api = AsyncMock(return_value="toca música")

        import io
        audio_data = io.BytesIO(b'test')
        result = await sink._transcribe_audio(audio_data)

        assert result == "toca música"
        sink._transcribe_openai_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_openai_api_returns_trimmed_text(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()

        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=TEST_GUILD_ID,
            zhipu_api_key=None,
            whisper_provider='openai-api',
            music_service=mock_music_service,
            openai_api_key='test_openai_key',
        )

        import io
        audio_data = io.BytesIO(b'RIFF')

        with patch('features.voice.voice_commands.build_openai_whisper_client', return_value=MagicMock()):
            with patch(
                'features.voice.voice_commands.transcribe_openai_whisper',
                return_value='toca música',
            ):
                result = await sink._transcribe_openai_api(audio_data)

        assert result == 'toca música'

    @pytest.mark.asyncio
    async def test_transcribe_openai_api_returns_none_without_key(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()

        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=TEST_GUILD_ID,
            zhipu_api_key=None,
            whisper_provider='openai-api',
            music_service=mock_music_service,
            openai_api_key=None,
        )

        import io
        result = await sink._transcribe_openai_api(io.BytesIO(b'RIFF'))
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_sidecar_sends_initial_prompt(self, sink_instance):
        sink, _, _, _ = sink_instance
        captured = {}

        class FakeFormData:
            def add_field(self, name, value, **kwargs):
                captured[name] = value

        import io
        audio_data = io.BytesIO(b'RIFF')

        with patch('features.voice.voice_commands.aiohttp.FormData', FakeFormData):
            with patch('aiohttp.ClientSession') as mock_session:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={'text': 'toca música'})
                mock_post_cm = MagicMock()
                mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post_cm.__aexit__ = AsyncMock(return_value=None)
                mock_session.return_value.__aenter__.return_value.post = MagicMock(return_value=mock_post_cm)

                result = await sink._transcribe_sidecar(audio_data)

        assert result == 'toca música'
        assert captured['prompt'] == WHISPER_INITIAL_PROMPT
        assert captured['file'] == b'RIFF'

    @pytest.mark.asyncio
    async def test_transcribe_sidecar_handles_timeout(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        import io
        audio_data = io.BytesIO(b'test')
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.side_effect = RuntimeError()
            result = await sink._transcribe_sidecar(audio_data)
            assert result is None


@pytest.mark.unit
class TestVoiceCommandSinkHealthMonitoring:
    def test_start_health_monitor_sets_flag(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        assert sink._health_monitor_started is False
        sink._start_health_monitor()
        assert sink._health_monitor_started is True

    def test_listener_inactive_when_not_listening(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_vc.is_connected.return_value = True
        mock_vc.is_listening.return_value = False

        assert sink._listener_inactive() is True

    def test_listener_inactive_when_healthy(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_vc.is_connected.return_value = True
        mock_vc.is_listening.return_value = True
        mock_vc._reader = None

        assert sink._listener_inactive() is False

    def test_listener_inactive_when_disconnected(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_vc.is_connected.return_value = False

        assert sink._listener_inactive() is False

    def test_listener_inactive_when_reader_has_error(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_vc.is_connected.return_value = True
        mock_vc.is_listening.return_value = True
        mock_reader = MagicMock()
        mock_reader.error = RuntimeError('router died')
        mock_vc._reader = mock_reader

        assert sink._listener_inactive() is True

    @pytest.mark.asyncio
    async def test_recover_listener_skips_when_already_recovering(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._recovering_listener = True
        sink._restart_listening = AsyncMock()
        sink._trigger_reconnection = AsyncMock()

        await sink._recover_listener()

        sink._restart_listening.assert_not_awaited()
        sink._trigger_reconnection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_recover_listener_falls_back_to_reconnect(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._restart_listening = AsyncMock(return_value=False)
        sink._trigger_reconnection = AsyncMock()

        await sink._recover_listener()

        sink._restart_listening.assert_awaited_once()
        sink._trigger_reconnection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recover_listener_restarts_listen_before_reconnect(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        sink._restart_listening = AsyncMock(return_value=True)
        sink._trigger_reconnection = AsyncMock()

        await sink._recover_listener()

        sink._restart_listening.assert_awaited_once()
        sink._trigger_reconnection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restart_listening_restarts_sink(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_vc.is_connected.return_value = True

        result = await sink._restart_listening()

        assert result is True
        mock_vc.listen.assert_called_once_with(sink)

    @pytest.mark.asyncio
    async def test_reconnect_voice_client_passes_saved_channel(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        mock_channel = MagicMock()
        mock_vc.channel = mock_channel
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()
        new_vc = MagicMock()
        sink.music_bot_ref = MagicMock()
        sink.music_bot_ref.reconnect_voice_client = AsyncMock(return_value=new_vc)

        result = await sink._reconnect_voice_client()

        assert result is True
        sink.music_bot_ref.reconnect_voice_client.assert_awaited_once_with(
            sink.guild_id, channel=mock_channel
        )
        assert sink._voice_client is new_vc

    @pytest.mark.asyncio
    async def test_cancel_listening_task_cancels_and_removes(self, sink_instance):
        import asyncio
        sink, _, _, _ = sink_instance
        
        async def dummy_task():
            await asyncio.sleep(10)
        
        task = asyncio.create_task(dummy_task())
        sink.listening_tasks[999] = task
        
        await sink._cancel_listening_task(999)
        
        assert 999 not in sink.listening_tasks
        assert task.cancelled()

    def test_get_text_channel_returns_channel(self, sink_instance):
        sink, mock_bot, _, _ = sink_instance
        
        mock_guild = MagicMock()
        mock_text_channel = MagicMock(spec=discord.TextChannel)
        mock_perms = MagicMock()
        mock_perms.send_messages = True
        mock_text_channel.permissions_for.return_value = mock_perms
        mock_guild.text_channels = [mock_text_channel]
        mock_bot.get_guild.return_value = mock_guild
        
        result = sink._get_text_channel()
        assert result == mock_text_channel

    def test_get_text_channel_returns_none_when_no_guild(self, sink_instance):
        sink, mock_bot, _, _ = sink_instance
        mock_bot.get_guild.return_value = None
        
        result = sink._get_text_channel()
        assert result is None


@pytest.mark.unit
class TestVoiceCommandErrorHandling:
    @pytest.mark.asyncio
    async def test_transcribe_sidecar_network_timeout(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        import io
        audio_data = io.BytesIO(b'test')
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.side_effect = asyncio.TimeoutError()
            result = await sink._transcribe_sidecar(audio_data)
            assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_sidecar_500_error(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        import io
        audio_data = io.BytesIO(b'test')
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value='Internal Server Error')
            
            mock_post = AsyncMock(return_value=mock_response)
            mock_session.return_value.__aenter__.return_value.post = mock_post
            
            result = await sink._transcribe_sidecar(audio_data)
            assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_zhipu_network_timeout(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()
        
        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=123,
            zhipu_api_key='test_key',
            whisper_provider='zhipu',
            music_service=mock_music_service
        )
        
        import io
        audio_data = io.BytesIO(b'test')
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.side_effect = asyncio.TimeoutError()
            result = await sink._transcribe_zhipu(audio_data)
            assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_zhipu_500_error(self):
        mock_bot = MagicMock()
        mock_vc = MagicMock()
        mock_music_service = MagicMock()
        
        sink = VoiceCommandSink(
            bot_instance=mock_bot,
            voice_client=mock_vc,
            guild_id=123,
            zhipu_api_key='test_key',
            whisper_provider='zhipu',
            music_service=mock_music_service
        )
        
        import io
        audio_data = io.BytesIO(b'test')
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value='Internal Server Error')
            
            mock_post = AsyncMock(return_value=mock_response)
            mock_session.return_value.__aenter__.return_value.post = mock_post
            
            result = await sink._transcribe_zhipu(audio_data)
            assert result is None

    def test_write_corrupt_audio_data(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'\x00\x01\x02\x03'
        
        sink.write(mock_user, mock_audio_data)
        
        assert mock_user.id in sink.audio_buffers
        assert len(sink.audio_buffers[mock_user.id]) == 1

    def test_write_invalid_pcm_format(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'not valid pcm data at all'
        
        sink.write(mock_user, mock_audio_data)
        
        assert mock_user.id in sink.audio_buffers

    @pytest.mark.asyncio
    async def test_concurrent_voice_commands(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(return_value="toca música")
        sink._route_speech = AsyncMock()
        mock_music_service.play_music = AsyncMock(return_value={'message': 'Playing...'})

        mock_member1 = MagicMock(spec=discord.Member)
        mock_member1.id = 999
        mock_member1.display_name = "User1"

        mock_member2 = MagicMock(spec=discord.Member)
        mock_member2.id = 888
        mock_member2.display_name = "User2"

        _fill_speech_buffer(sink, 999)
        _fill_speech_buffer(sink, 888)
        
        await asyncio.gather(
            sink.process_speech(mock_member1),
            sink.process_speech(mock_member2)
        )
        
        assert sink._transcribe_audio.call_count == 2
        assert sink._route_speech.call_count == 2

    @pytest.mark.asyncio
    async def test_voice_client_disconnection_mid_processing(self, sink_instance):
        sink, _, mock_vc, _ = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(return_value="toca música")
        sink._route_speech = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"

        _fill_speech_buffer(sink, 999)

        mock_vc.is_connected.return_value = False
        sink._voice_client = None
        
        await sink.process_speech(mock_member)
        
        assert sink._transcribe_audio.called
        assert sink._route_speech.called

    def test_audio_buffer_overflow(self, sink_instance):
        sink, _, _, _ = sink_instance
        
        mock_user = MagicMock(spec=discord.Member)
        mock_user.id = 999
        mock_audio_data = MagicMock()
        mock_audio_data.pcm = b'audio_data'
        
        for _ in range(200):
            sink.write(mock_user, mock_audio_data)
        
        assert len(sink.audio_buffers[999]) <= 150

    @pytest.mark.asyncio
    async def test_process_speech_handles_transcription_failure(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(return_value=None)
        sink._route_speech = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"

        _fill_speech_buffer(sink, 999)
        
        await sink.process_speech(mock_member)
        
        assert sink._transcribe_audio.called
        sink._route_speech.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_speech_handles_empty_transcription(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(return_value="")
        sink._route_speech = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"

        _fill_speech_buffer(sink, 999)
        
        await sink.process_speech(mock_member)
        
        assert sink._transcribe_audio.called
        sink._route_speech.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_speech_handles_exception_during_transcription(self, sink_instance):
        sink, _, _, _ = sink_instance
        sink._combine_audio_chunks = MagicMock()
        sink._transcribe_audio = AsyncMock(side_effect=Exception("Transcription error"))
        sink._route_speech = AsyncMock()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 999
        mock_member.display_name = "TestUser"

        _fill_speech_buffer(sink, 999)
        
        await sink.process_speech(mock_member)
        
        assert sink._transcribe_audio.called
        sink._route_speech.assert_not_called()


@pytest.mark.unit
class TestVoiceRecvPatches:
    def test_apply_voice_recv_patches_is_idempotent(self):
        from features.voice import voice_recv_patches

        voice_recv_patches._patched = False
        voice_recv_patches.apply_voice_recv_patches()
        voice_recv_patches.apply_voice_recv_patches()
        assert voice_recv_patches._patched is True
