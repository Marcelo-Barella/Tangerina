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


@pytest.mark.unit
class TestJoinVoicePreconditions:
    @pytest.mark.asyncio
    async def test_returns_none_when_bot_never_ready(self):
        bot = MagicMock()
        bot.is_ready.return_value = False
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"), patch(
            "features.music.music_bot.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is None
        sleep.assert_awaited_once_with(1)
        bot.get_guild.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_guild_missing(self):
        bot = MagicMock()
        bot.is_ready.return_value = True
        bot.get_guild.return_value = None
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"):
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_channel_fetch_forbidden(self):
        bot = MagicMock()
        bot.is_ready.return_value = True
        guild = MagicMock()
        guild.get_channel.return_value = None
        guild.fetch_channel = AsyncMock(side_effect=discord.errors.Forbidden(MagicMock(), "nope"))
        bot.get_guild.return_value = guild
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"):
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_channel_cannot_connect(self):
        bot = MagicMock()
        bot.is_ready.return_value = True
        guild = MagicMock()
        text_channel = MagicMock(spec=["id", "name"])
        guild.get_channel.return_value = text_channel
        bot.get_guild.return_value = guild
        music_bot = MusicBot(bot)
        with patch.object(music_bot, "_check_nacl"):
            result = await music_bot.join_voice_channel(123, 456, voice_recv_module=False)
        assert result is None
