import discord
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from features.music.music_bot import MusicBot


def _ready_bot(channel_id=456):
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.voice_clients = []
    guild = MagicMock()
    channel = MagicMock()
    channel.id = channel_id
    channel.connect = AsyncMock()
    guild.get_channel.return_value = channel
    bot.get_guild.return_value = guild
    return bot, channel


@pytest.mark.unit
class TestJoinVoiceTransportRetry:
    @pytest.mark.asyncio
    async def test_retries_closing_transport_and_succeeds(self):
        bot, _channel = _ready_bot()
        music_bot = MusicBot(bot)
        voice_client = MagicMock()
        with patch.object(music_bot, "_check_nacl"), patch.object(
            music_bot,
            "_move_or_connect",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("Closing transport"), voice_client],
        ) as move, patch(
            "features.music.music_bot.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is voice_client
        assert move.await_count == 2
        sleep.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_retries_connection_reset_then_returns_none(self):
        bot, _channel = _ready_bot()
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"), patch.object(
            music_bot,
            "_move_or_connect",
            new_callable=AsyncMock,
            side_effect=[
                ConnectionResetError("Connection reset by peer"),
                RuntimeError("still down"),
            ],
        ), patch(
            "features.music.music_bot.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_reraises_unrelated_client_exception(self):
        bot, _channel = _ready_bot()
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"), patch.object(
            music_bot,
            "_move_or_connect",
            new_callable=AsyncMock,
            side_effect=discord.errors.ClientException("already in a voice channel"),
        ), patch(
            "features.music.music_bot.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            with pytest.raises(discord.errors.ClientException):
                await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        sleep.assert_not_called()
