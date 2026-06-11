import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from features.tts.tts_handler import (
    _reduce_music_volume_for_tts,
    _restore_music_volume,
    speak_tts_unified,
)
from tests.conftest import TEST_CHANNEL_ID, TEST_GUILD_ID


def _make_voice_client(*, playing=False, paused=False, has_volume_source=False):
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = playing
    voice_client.is_paused.return_value = paused
    if has_volume_source:
        source = MagicMock(spec=discord.PCMVolumeTransformer)
        source.volume = 0.8
        voice_client.source = source
    else:
        voice_client.source = None
    return voice_client


def _make_music_bot(*, voice_client=None, music_source=None, current_song=None):
    music_bot = MagicMock()
    music_bot.voice_clients = {}
    music_bot.original_volumes = {}
    music_bot.current_songs = {}
    music_bot.main_loop = None
    music_bot.join_voice_channel = AsyncMock(return_value=voice_client)
    music_bot.get_current_music_source = MagicMock(return_value=music_source)
    if current_song is not None:
        music_bot.current_songs[TEST_GUILD_ID] = current_song
    if voice_client is not None:
        music_bot.voice_clients[TEST_GUILD_ID] = voice_client
    return music_bot


async def _call_speak_tts_unified(**overrides):
    defaults = {
        "guild_id": TEST_GUILD_ID,
        "channel_id": TEST_CHANNEL_ID,
        "text": "hello",
        "tts_provider": "omnivoice",
        "tts_providers": {"omnivoice": MagicMock()},
        "tts_generate": None,
        "set_eleven_api_key": None,
        "ELEVEN_API_KEY": None,
        "ELEVEN_VOICE_ID": None,
        "ELEVEN_MODEL": None,
        "ELEVEN_OUTPUT_FORMAT": None,
        "music_bot": _make_music_bot(),
        "_resolve_voice_channel": AsyncMock(return_value=(TEST_CHANNEL_ID, None)),
        "ytdl": MagicMock(),
        "YTDLSource": MagicMock(),
    }
    defaults.update(overrides)
    return await speak_tts_unified(**defaults)


@pytest.mark.unit
class TestSpeakTtsUnified:
    async def test_http_provider_not_configured_returns_error(self):
        result = await _call_speak_tts_unified(tts_providers={})

        assert result == {"success": False, "error": "OmniVoice TTS not configured"}

    async def test_http_provider_cleans_up_when_channel_resolution_fails(self, tmp_path):
        audio_file = str(tmp_path / "speech.wav")
        tmp_path.joinpath("speech.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech.return_value = audio_file
        music_bot = _make_music_bot()

        with patch("features.tts.tts_handler.cleanup_tts_file") as cleanup:
            result = await _call_speak_tts_unified(
                tts_providers={"omnivoice": tts_client},
                music_bot=music_bot,
                _resolve_voice_channel=AsyncMock(return_value=(None, "Channel not found")),
            )

        assert result == {"success": False, "error": "Channel not found"}
        cleanup.assert_called_once_with(audio_file)

    async def test_http_provider_plays_without_music(self, tmp_path):
        audio_file = str(tmp_path / "speech.wav")
        tmp_path.joinpath("speech.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech.return_value = audio_file
        voice_client = _make_voice_client()
        music_bot = _make_music_bot(voice_client=voice_client)

        with patch("features.tts.tts_handler.discord.FFmpegPCMAudio") as ffmpeg_audio:
            result = await _call_speak_tts_unified(
                tts_providers={"omnivoice": tts_client},
                music_bot=music_bot,
            )

        assert result == {"success": True, "message": "Speaking with OmniVoice..."}
        voice_client.play.assert_called_once()
        ffmpeg_audio.assert_called_once_with(audio_file, options="-vn")

    async def test_mixed_playback_returns_success_after_mixing_completes(self, tmp_path):
        audio_file = str(tmp_path / "speech.wav")
        tmp_path.joinpath("speech.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech.return_value = audio_file
        voice_client = _make_voice_client(playing=True, has_volume_source=True)
        music_bot = _make_music_bot(
            voice_client=voice_client,
            music_source={"url": "http://music.example/stream"},
            current_song={"url": "http://music.example/page"},
        )

        with patch(
            "features.tts.tts_handler._play_tts_with_mixing", new_callable=AsyncMock
        ) as play_mixing:
            result = await _call_speak_tts_unified(
                tts_providers={"omnivoice": tts_client},
                music_bot=music_bot,
            )

        play_mixing.assert_awaited_once()
        assert result == {
            "success": True,
            "message": "Speaking with OmniVoice and music...",
        }
        voice_client.play.assert_not_called()

    async def test_mixed_playback_falls_back_when_mixing_raises(self, tmp_path):
        audio_file = str(tmp_path / "speech.wav")
        tmp_path.joinpath("speech.wav").write_bytes(b"RIFF")

        tts_client = MagicMock()
        tts_client.generate_speech.return_value = audio_file
        voice_client = _make_voice_client(playing=True, has_volume_source=True)
        music_bot = _make_music_bot(
            voice_client=voice_client,
            music_source={"url": "http://music.example/stream"},
            current_song={"url": "http://music.example/page"},
        )

        with (
            patch(
                "features.tts.tts_handler._play_tts_with_mixing",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ffmpeg unavailable"),
            ),
            patch("features.tts.tts_handler.discord.FFmpegPCMAudio"),
        ):
            result = await _call_speak_tts_unified(
                tts_providers={"omnivoice": tts_client},
                music_bot=music_bot,
            )

        voice_client.pause.assert_called_once()
        voice_client.play.assert_called_once()
        assert result == {"success": True, "message": "Speaking with OmniVoice..."}

    async def test_elevenlabs_unavailable_without_api_key(self):
        result = await _call_speak_tts_unified(
            tts_provider="elevenlabs",
            tts_providers={},
            tts_generate=MagicMock(),
            ELEVEN_API_KEY=None,
        )

        assert result == {
            "success": False,
            "error": "TTS unavailable: missing dependency or ELEVEN_API_KEY",
        }


@pytest.mark.unit
class TestMusicVolumeHelpers:
    def test_reduce_music_volume_stores_original_and_lowers_volume(self):
        voice_client = _make_voice_client(playing=True, has_volume_source=True)
        music_bot = _make_music_bot(voice_client=voice_client)

        original = _reduce_music_volume_for_tts(TEST_GUILD_ID, music_bot)

        assert original == 0.8
        assert music_bot.original_volumes[TEST_GUILD_ID] == 0.8
        assert voice_client.source.volume == 0.2

    def test_reduce_music_volume_returns_none_when_not_playing(self):
        voice_client = _make_voice_client(playing=False, has_volume_source=True)
        music_bot = _make_music_bot(voice_client=voice_client)

        assert _reduce_music_volume_for_tts(TEST_GUILD_ID, music_bot) is None

    def test_restore_music_volume_uses_stored_volume(self):
        voice_client = _make_voice_client(has_volume_source=True)
        music_bot = _make_music_bot(voice_client=voice_client)
        music_bot.original_volumes[TEST_GUILD_ID] = 0.75
        voice_client.source.volume = 0.2

        _restore_music_volume(TEST_GUILD_ID, None, music_bot)

        assert voice_client.source.volume == 0.75
        assert TEST_GUILD_ID not in music_bot.original_volumes
