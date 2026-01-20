import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from features.voice.voice_commands import (
    WAKE_WORD,
    CANCEL_KEYWORDS,
    VOLUME_MIN,
    VOLUME_MAX,
    LISTENING_DURATION,
    VoiceCommandSink
)

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
        guild_id=123,
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
        assert sink.guild_id == 123
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
        
        sink.write(mock_user, mock_audio_data)
        assert mock_user.id not in sink.audio_buffers


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
        mock_music_service.set_volume.assert_called_with(123, 80)

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
        
        sink.audio_buffers[999].append(b'chunk1')
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
        mock_music_service.stop_music.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_handle_skip_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.skip_music = AsyncMock(return_value={'message': 'Skipped'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_skip(mock_channel, "pula")
        mock_music_service.skip_music.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_handle_pause_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.pause_music = AsyncMock(return_value={'message': 'Paused'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_pause(mock_channel, "pausa")
        mock_music_service.pause_music.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_handle_resume_calls_music_service(self, sink_instance):
        sink, _, _, mock_music_service = sink_instance
        mock_music_service.resume_music = AsyncMock(return_value={'message': 'Resumed'})
        
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        
        await sink._handle_resume(mock_channel, "continua")
        mock_music_service.resume_music.assert_called_once_with(123)

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
        mock_music_service.leave_music.assert_called_once_with(123)


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
            guild_id=123,
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
