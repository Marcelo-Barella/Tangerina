import importlib
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MODULE = "features.tts.tts_handler"
_SAVED_DISCORD = sys.modules.get("discord")


def _load_tts_handler():
    discord_module = ModuleType("discord")
    discord_module.AudioSource = object
    discord_module.PCMVolumeTransformer = MagicMock
    discord_module.FFmpegPCMAudio = MagicMock
    sys.modules["discord"] = discord_module
    sys.modules.pop(_MODULE, None)
    return importlib.import_module(_MODULE)


@pytest.fixture
def tts_handler():
    return _load_tts_handler()


@pytest.fixture(autouse=True)
def _restore_discord_module():
    yield
    sys.modules.pop(_MODULE, None)
    if _SAVED_DISCORD is None:
        sys.modules.pop("discord", None)
    else:
        sys.modules["discord"] = _SAVED_DISCORD


def _base_kwargs():
    music_bot = MagicMock()
    music_bot.join_voice_channel = AsyncMock()
    music_bot.get_current_music_source = MagicMock(return_value=None)
    music_bot.main_loop = None
    music_bot.voice_clients = {}
    music_bot.original_volumes = {}
    music_bot.current_songs = {}
    return {
        "guild_id": 1,
        "channel_id": 2,
        "text": "hello",
        "tts_generate": None,
        "set_eleven_api_key": None,
        "ELEVEN_API_KEY": "",
        "ELEVEN_VOICE_ID": "voice",
        "ELEVEN_MODEL": "model",
        "ELEVEN_OUTPUT_FORMAT": "mp3",
        "music_bot": music_bot,
        "ytdl": MagicMock(),
        "YTDLSource": MagicMock(),
    }


@pytest.mark.unit
class TestSpeakTtsUnifiedHttpCleanup:
    @pytest.mark.asyncio
    async def test_cleans_up_audio_when_channel_resolution_fails(self, tts_handler):
        mock_client = MagicMock()
        audio_file = "/tmp/tangerina-tts-test.wav"
        mock_client.generate_speech.return_value = audio_file
        kwargs = _base_kwargs()
        kwargs.update(
            {
                "tts_provider": "omnivoice",
                "tts_providers": {"omnivoice": mock_client},
                "_resolve_voice_channel": AsyncMock(return_value=(None, "channel error")),
            }
        )

        with patch.object(tts_handler, "cleanup_tts_file") as cleanup:
            result = await tts_handler.speak_tts_unified(**kwargs)

        assert result == {"success": False, "error": "channel error"}
        cleanup.assert_called_once_with(audio_file)

    @pytest.mark.asyncio
    async def test_cleans_up_audio_when_join_voice_channel_fails(self, tts_handler):
        mock_client = MagicMock()
        audio_file = "/tmp/tangerina-tts-join-fail.wav"
        mock_client.generate_speech.return_value = audio_file
        kwargs = _base_kwargs()
        kwargs["music_bot"].join_voice_channel.return_value = None
        kwargs.update(
            {
                "tts_provider": "piper",
                "tts_providers": {"piper": mock_client},
                "_resolve_voice_channel": AsyncMock(return_value=(99, None)),
            }
        )

        with patch.object(tts_handler, "cleanup_tts_file") as cleanup:
            result = await tts_handler.speak_tts_unified(**kwargs)

        assert result == {"success": False, "error": "Failed to join voice channel"}
        cleanup.assert_called_once_with(audio_file)

    @pytest.mark.asyncio
    async def test_returns_error_when_http_provider_not_configured(self, tts_handler):
        kwargs = _base_kwargs()
        kwargs.update(
            {
                "tts_provider": "omnivoice",
                "tts_providers": {},
                "_resolve_voice_channel": AsyncMock(),
            }
        )

        result = await tts_handler.speak_tts_unified(**kwargs)

        assert result == {"success": False, "error": "OmniVoice TTS not configured"}
