import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_CHANNEL_ID, TEST_GUILD_ID

if "discord" not in sys.modules:
    discord = ModuleType("discord")
    discord.FFmpegPCMAudio = MagicMock()
    discord.PCMVolumeTransformer = MagicMock()
    discord.AudioSource = type("AudioSource", (), {})
    sys.modules["discord"] = discord

from features.tts.tts_handler import speak_tts_unified


def _base_kwargs(music_bot, resolve_channel):
    return {
        "guild_id": TEST_GUILD_ID,
        "channel_id": TEST_CHANNEL_ID,
        "text": "hello",
        "tts_providers": {"omnivoice": MagicMock()},
        "tts_generate": None,
        "set_eleven_api_key": None,
        "ELEVEN_API_KEY": None,
        "ELEVEN_VOICE_ID": "voice",
        "ELEVEN_MODEL": "model",
        "ELEVEN_OUTPUT_FORMAT": "mp3",
        "music_bot": music_bot,
        "_resolve_voice_channel": resolve_channel,
        "ytdl": MagicMock(),
        "YTDLSource": MagicMock(),
    }


@pytest.mark.unit
class TestSpeakTtsUnifiedCleanup:
    @pytest.mark.asyncio
    async def test_omnivoice_cleans_up_when_channel_resolve_fails(self, mock_music_bot):
        audio_path = "/tmp/tts-test.wav"
        tts_client = MagicMock()
        tts_client.generate_speech = MagicMock(return_value=audio_path)
        resolve_channel = AsyncMock(return_value=(None, "Guild not found"))
        kwargs = _base_kwargs(mock_music_bot, resolve_channel)
        kwargs["tts_provider"] = "omnivoice"
        kwargs["tts_providers"]["omnivoice"] = tts_client

        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)

        assert result["success"] is False
        cleanup.assert_called_once_with(audio_path)

    @pytest.mark.asyncio
    async def test_omnivoice_cleans_up_when_join_fails(self, mock_music_bot):
        audio_path = "/tmp/tts-test.wav"
        tts_client = MagicMock()
        tts_client.generate_speech = MagicMock(return_value=audio_path)
        resolve_channel = AsyncMock(return_value=(TEST_CHANNEL_ID, None))
        mock_music_bot.join_voice_channel = AsyncMock(return_value=None)
        kwargs = _base_kwargs(mock_music_bot, resolve_channel)
        kwargs["tts_provider"] = "omnivoice"
        kwargs["tts_providers"]["omnivoice"] = tts_client

        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)

        assert result["success"] is False
        assert "join" in result["error"].lower()
        cleanup.assert_called_once_with(audio_path)

    @pytest.mark.asyncio
    async def test_elevenlabs_does_not_cleanup_on_resolve_failure(self, mock_music_bot):
        resolve_channel = AsyncMock(return_value=(None, "Guild not found"))
        kwargs = _base_kwargs(mock_music_bot, resolve_channel)
        kwargs["tts_provider"] = "elevenlabs"
        kwargs["ELEVEN_API_KEY"] = "test-key"
        kwargs["tts_generate"] = MagicMock(return_value=b"mp3bytes")

        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await speak_tts_unified(**kwargs)

        assert result["success"] is False
        cleanup.assert_not_called()
