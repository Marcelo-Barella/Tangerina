from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.tts.tts_handler import _play_tts_with_mixing


@pytest.mark.unit
class TestTtsHandlerMixing:
    @pytest.mark.asyncio
    async def test_mixed_after_play_passes_error_to_cleanup_callback(self):
        voice_client = MagicMock()
        music_bot = MagicMock()
        music_bot.main_loop = None
        current_song = {"url": "https://example.com/song"}
        cleanup_callback = MagicMock()

        mixed_source_cls = MagicMock()
        mixed_source = mixed_source_cls.return_value

        handler_patches = patch.multiple(
            "features.tts.tts_handler",
            MixedAudioSource=mixed_source_cls,
            _get_fresh_music_url=AsyncMock(return_value="https://example.com/stream"),
            _resume_music_after_tts=AsyncMock(),
        )
        with handler_patches, patch("asyncio.sleep", AsyncMock()):
            await _play_tts_with_mixing(
                guild_id=1,
                voice_client=voice_client,
                music_source_info={"url": "https://example.com/stream"},
                tts_file="/tmp/tts.wav",
                current_song=current_song,
                music_bot=music_bot,
                ytdl=MagicMock(),
                YTDLSource=MagicMock(),
                music_volume=0.2,
                cleanup_callback=cleanup_callback,
            )

        after_play = voice_client.play.call_args.kwargs["after"]
        after_play(None)

        cleanup_callback.assert_called_once_with(None)
        mixed_source.cleanup.assert_called_once()
