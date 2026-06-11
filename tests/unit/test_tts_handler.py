import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.tts.tts_handler import speak_tts_unified


@pytest.mark.unit
class TestSpeakTtsUnified:
    @pytest.fixture
    def music_bot(self):
        bot = MagicMock()
        bot.voice_clients = {}
        bot.current_songs = {}
        bot.original_volumes = {}
        bot.main_loop = None
        bot.get_current_music_source = MagicMock(return_value=None)
        bot.join_voice_channel = AsyncMock(return_value=MagicMock())
        return bot

    @pytest.fixture
    def resolve_channel(self):
        async def _resolve(guild_id, channel_id):
            return channel_id, None

        return _resolve

    def _run(self, **kwargs):
        defaults = {
            "guild_id": 1,
            "channel_id": 2,
            "text": "hello",
            "tts_provider": "omnivoice",
            "tts_providers": {},
            "tts_generate": None,
            "set_eleven_api_key": None,
            "ELEVEN_API_KEY": "",
            "ELEVEN_VOICE_ID": "",
            "ELEVEN_MODEL": "",
            "ELEVEN_OUTPUT_FORMAT": "",
            "music_bot": kwargs.pop("music_bot"),
            "_resolve_voice_channel": kwargs.pop("resolve_channel"),
            "ytdl": MagicMock(),
            "YTDLSource": MagicMock(),
        }
        defaults.update(kwargs)
        return asyncio.run(speak_tts_unified(**defaults))

    def test_omnivoice_not_configured_returns_error(self, music_bot, resolve_channel):
        result = self._run(
            music_bot=music_bot,
            resolve_channel=resolve_channel,
            tts_provider="omnivoice",
            tts_providers={},
        )
        assert result == {"success": False, "error": "OmniVoice TTS not configured"}

    def test_piper_not_configured_returns_error(self, music_bot, resolve_channel):
        result = self._run(
            music_bot=music_bot,
            resolve_channel=resolve_channel,
            tts_provider="piper",
            tts_providers={},
        )
        assert result == {"success": False, "error": "Piper TTS not configured"}

    def test_omnivoice_happy_path_plays_audio(self, music_bot, resolve_channel, tmp_path):
        audio_path = str(tmp_path / "out.wav")
        tmp_path.joinpath("out.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech = MagicMock(return_value=audio_path)
        voice_client = MagicMock()
        music_bot.join_voice_channel = AsyncMock(return_value=voice_client)

        mock_ffmpeg = MagicMock()
        with patch("features.tts.tts_handler.discord.FFmpegPCMAudio", mock_ffmpeg):
            result = self._run(
                music_bot=music_bot,
                resolve_channel=resolve_channel,
                tts_providers={"omnivoice": tts_client},
            )

        assert result["success"] is True
        assert "OmniVoice" in result["message"]
        voice_client.play.assert_called_once()
        mock_ffmpeg.assert_called_once_with(audio_path, options="-vn")

    def test_omnivoice_cleans_up_on_channel_resolve_failure(self, music_bot, tmp_path):
        audio_path = str(tmp_path / "out.wav")
        tmp_path.joinpath("out.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech = MagicMock(return_value=audio_path)

        async def resolve_fail(guild_id, channel_id):
            return None, "Channel not found"

        with patch("features.tts.tts_handler.cleanup_tts_file") as mock_cleanup:
            result = self._run(
                music_bot=music_bot,
                resolve_channel=resolve_fail,
                tts_providers={"omnivoice": tts_client},
            )

        assert result == {"success": False, "error": "Channel not found"}
        mock_cleanup.assert_called_once_with(audio_path)

    def test_omnivoice_cleans_up_on_voice_join_failure(self, music_bot, tmp_path):
        audio_path = str(tmp_path / "out.wav")
        tmp_path.joinpath("out.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech = MagicMock(return_value=audio_path)
        music_bot.join_voice_channel = AsyncMock(return_value=None)

        async def resolve_ok(guild_id, channel_id):
            return channel_id, None

        with patch("features.tts.tts_handler.cleanup_tts_file") as mock_cleanup:
            result = self._run(
                music_bot=music_bot,
                resolve_channel=resolve_ok,
                tts_providers={"omnivoice": tts_client},
            )

        assert result == {"success": False, "error": "Failed to join voice channel"}
        mock_cleanup.assert_called_once_with(audio_path)
