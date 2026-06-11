from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.tts.tts_handler import speak_tts_unified


def _make_music_bot():
    music_bot = MagicMock()
    music_bot.voice_clients = {}
    music_bot.current_songs = {}
    music_bot.original_volumes = {}
    music_bot.main_loop = MagicMock()
    music_bot.get_current_music_source = MagicMock(return_value=None)
    music_bot.join_voice_channel = AsyncMock()
    return music_bot


def _base_kwargs(**overrides):
    tts_client = MagicMock()
    tts_client.generate_speech = MagicMock(return_value="/tmp/test-audio.wav")
    music_bot = _make_music_bot()
    kwargs = {
        "guild_id": 123,
        "channel_id": 456,
        "text": "hello",
        "tts_provider": "omnivoice",
        "tts_providers": {"omnivoice": tts_client},
        "tts_generate": None,
        "set_eleven_api_key": None,
        "ELEVEN_API_KEY": None,
        "ELEVEN_VOICE_ID": None,
        "ELEVEN_MODEL": None,
        "ELEVEN_OUTPUT_FORMAT": None,
        "music_bot": music_bot,
        "_resolve_voice_channel": AsyncMock(return_value=(456, None)),
        "ytdl": MagicMock(),
        "YTDLSource": MagicMock(),
    }
    kwargs.update(overrides)
    return kwargs, tts_client, music_bot


@pytest.mark.unit
class TestSpeakTtsUnified:
    @pytest.mark.asyncio
    async def test_http_provider_not_configured(self):
        kwargs, _, _ = _base_kwargs(tts_providers={})
        result = await speak_tts_unified(**kwargs)
        assert result == {"success": False, "error": "OmniVoice TTS not configured"}

    @pytest.mark.asyncio
    async def test_channel_resolve_failure_cleans_up_omnivoice_audio(self):
        kwargs, _, _ = _base_kwargs(
            _resolve_voice_channel=AsyncMock(return_value=(None, "Guild not found")),
        )
        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)
        assert result == {"success": False, "error": "Guild not found"}
        cleanup.assert_called_once_with("/tmp/test-audio.wav")

    @pytest.mark.asyncio
    async def test_channel_resolve_failure_cleans_up_piper_audio(self):
        piper_client = MagicMock()
        piper_client.generate_speech = MagicMock(return_value="/tmp/piper-audio.wav")
        kwargs, _, _ = _base_kwargs(
            tts_provider="piper",
            tts_providers={"piper": piper_client},
            _resolve_voice_channel=AsyncMock(return_value=(None, "Invalid channel")),
        )
        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)
        assert result == {"success": False, "error": "Invalid channel"}
        cleanup.assert_called_once_with("/tmp/piper-audio.wav")

    @pytest.mark.asyncio
    async def test_join_failure_cleans_up_audio(self):
        kwargs, _, music_bot = _base_kwargs()
        music_bot.join_voice_channel = AsyncMock(return_value=None)
        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)
        assert result == {"success": False, "error": "Failed to join voice channel"}
        cleanup.assert_called_once_with("/tmp/test-audio.wav")

    @pytest.mark.asyncio
    async def test_successful_http_provider_playback(self):
        kwargs, _, music_bot = _base_kwargs()
        voice_client = MagicMock()
        voice_client.is_paused = MagicMock(return_value=False)
        music_bot.join_voice_channel = AsyncMock(return_value=voice_client)

        with patch("features.tts.tts_handler.discord.FFmpegPCMAudio", return_value=MagicMock()):
            result = await speak_tts_unified(**kwargs)

        assert result == {"success": True, "message": "Speaking with OmniVoice..."}
        voice_client.play.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_playback_failure_falls_back_to_pause_and_play(self):
        kwargs, _, music_bot = _base_kwargs()
        voice_client = MagicMock()
        voice_client.is_paused = MagicMock(return_value=False)
        music_bot.join_voice_channel = AsyncMock(return_value=voice_client)
        music_bot.get_current_music_source = MagicMock(
            return_value={"url": "http://music.example/stream"}
        )

        with (
            patch("features.tts.tts_handler.discord.FFmpegPCMAudio", return_value=MagicMock()),
            patch(
                "features.tts.tts_handler._reduce_music_volume_for_tts",
                return_value=1.0,
            ),
            patch(
                "features.tts.tts_handler._play_tts_with_mixing",
                AsyncMock(side_effect=RuntimeError("ffmpeg failed")),
            ),
        ):
            result = await speak_tts_unified(**kwargs)

        assert result == {"success": True, "message": "Speaking with OmniVoice..."}
        voice_client.pause.assert_called_once()
        voice_client.play.assert_called_once()
