import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from features.discord.chatbot_reply import (
    DISCORD_MESSAGE_LIMIT,
    post_chatbot_reply,
    should_post_chatbot_reply,
    should_respond_with_chatbot,
    split_discord_message,
)


def _make_message(
    *,
    content: str | None = "",
    author_bot: bool = False,
    guild: object | None = object(),
    bot_mentioned: bool = False,
):
    message = MagicMock()
    message.content = content
    message.author.bot = author_bot
    message.guild = guild
    bot_user = MagicMock()
    bot_user.mentioned_in = MagicMock(return_value=bot_mentioned)
    return message, bot_user


@pytest.mark.unit
class TestShouldRespondWithChatbot:
    def test_bot_author_returns_false(self):
        message, bot_user = _make_message(author_bot=True, content="tangerina")
        assert should_respond_with_chatbot(message, bot_user) is False

    def test_tangerina_in_content_returns_true(self):
        message, bot_user = _make_message(content="hey tangerina play music")
        assert should_respond_with_chatbot(message, bot_user) is True

    def test_bot_mention_returns_true(self):
        message, bot_user = _make_message(content="hello", bot_mentioned=True)
        assert should_respond_with_chatbot(message, bot_user) is True

    def test_dm_returns_true(self):
        message, bot_user = _make_message(content="hello", guild=None)
        assert should_respond_with_chatbot(message, bot_user) is True

    def test_unrelated_guild_message_returns_false(self):
        message, bot_user = _make_message(content="hello everyone")
        assert should_respond_with_chatbot(message, bot_user) is False

    def test_none_content_does_not_crash(self):
        message, bot_user = _make_message(content=None)
        assert should_respond_with_chatbot(message, bot_user) is False

    def test_empty_content_returns_false_in_guild(self):
        message, bot_user = _make_message(content="   ")
        assert should_respond_with_chatbot(message, bot_user) is False

    def test_no_bot_user_mention_check_skipped(self):
        message, _ = _make_message(content="tangerina")
        assert should_respond_with_chatbot(message, None) is True

    def test_bot_role_mention_returns_true(self):
        message = MagicMock()
        message.content = "<@&1389329598915022850> entra na chamada"
        message.author.bot = False
        message.guild = MagicMock()
        bot_role = MagicMock()
        bot_role.id = 1389329598915022850
        message.guild.me = MagicMock()
        message.guild.me.roles = [bot_role]
        message.role_mentions = [bot_role]
        bot_user = MagicMock()
        bot_user.mentioned_in = MagicMock(return_value=False)
        assert should_respond_with_chatbot(message, bot_user) is True

    def test_unrelated_role_mention_returns_false(self):
        message = MagicMock()
        message.content = "<@&999> hello"
        message.author.bot = False
        message.guild = MagicMock()
        other_role = MagicMock()
        other_role.id = 999
        message.guild.me = MagicMock()
        message.guild.me.roles = [MagicMock(id=111)]
        message.role_mentions = [other_role]
        bot_user = MagicMock()
        bot_user.mentioned_in = MagicMock(return_value=False)
        assert should_respond_with_chatbot(message, bot_user) is False

    def test_bot_role_mention_works_without_bot_user(self):
        message = MagicMock()
        message.content = "<@&1389329598915022850> entra na chamada"
        message.author.bot = False
        message.guild = MagicMock()
        bot_role = MagicMock()
        bot_role.id = 1389329598915022850
        message.guild.me = MagicMock()
        message.guild.me.roles = [bot_role]
        message.role_mentions = [bot_role]
        assert should_respond_with_chatbot(message, None) is True

    def test_role_mention_without_guild_me_returns_false(self):
        message = MagicMock()
        message.content = "<@&1389329598915022850> entra na chamada"
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.me = None
        message.role_mentions = [MagicMock(id=1389329598915022850)]
        bot_user = MagicMock()
        bot_user.mentioned_in = MagicMock(return_value=False)
        assert should_respond_with_chatbot(message, bot_user) is False


@pytest.mark.unit
class TestShouldPostChatbotReply:
    def test_empty_response_returns_none(self):
        assert should_post_chatbot_reply("", []) is None

    def test_whitespace_only_returns_none(self):
        assert should_post_chatbot_reply("   \n\t  ", []) is None

    def test_none_response_returns_none(self):
        assert should_post_chatbot_reply(None, []) is None

    def test_non_string_response_returns_none(self):
        assert should_post_chatbot_reply(123, []) is None

    def test_acao_executada_returns_none(self):
        assert should_post_chatbot_reply("Ação executada.", []) is None

    def test_acao_executada_com_sucesso_returns_none(self):
        assert should_post_chatbot_reply("Ação executada com sucesso!", []) is None

    def test_entrei_no_canal_prefix_returns_none(self):
        assert should_post_chatbot_reply("Entrei no canal Geral!", []) is None

    def test_conversational_text_returns_normalized(self):
        assert (
            should_post_chatbot_reply("Claro, posso te ajudar com isso!", [])
            == "Claro, posso te ajudar com isso!"
        )

    def test_error_string_returns_normalized(self):
        assert (
            should_post_chatbot_reply("Erro ao executar ação: Channel not found", [])
            == "Erro ao executar ação: Channel not found"
        )

    def test_successful_send_mensagem_suppresses_matching_reply(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "parameters": {"text": "Claro, posso te ajudar!"},
                "result": {"success": True},
            }
        ]
        assert should_post_chatbot_reply("Claro, posso te ajudar!", tool_calls) is None

    def test_successful_send_mensagem_does_not_suppress_different_reply(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "parameters": {"text": "Entendido!"},
                "result": {"success": True},
            }
        ]
        assert should_post_chatbot_reply(
            "A capital da França é Paris e fica na Europa.",
            tool_calls,
        ) == "A capital da França é Paris e fica na Europa."

    def test_cross_channel_send_does_not_suppress(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "parameters": {"channel_id": 999, "text": "Claro, posso te ajudar!"},
                "result": {"success": True},
            }
        ]
        assert should_post_chatbot_reply(
            "Claro, posso te ajudar!",
            tool_calls,
            channel_id=111,
        ) == "Claro, posso te ajudar!"

    def test_joined_send_texts_suppresses_aggregate(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "parameters": {"text": "Primeiro."},
                "result": {"success": True},
            },
            {
                "tool": "SEND_Mensagem",
                "parameters": {"text": "Segundo."},
                "result": {"success": True},
            },
        ]
        assert should_post_chatbot_reply("Primeiro. Segundo.", tool_calls) is None

    def test_successful_send_mensagem_without_text_does_not_suppress(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "result": {"success": True},
            }
        ]
        assert should_post_chatbot_reply("Claro, posso te ajudar!", tool_calls) == "Claro, posso te ajudar!"

    def test_failed_send_mensagem_does_not_suppress(self):
        tool_calls = [
            {
                "tool": "SEND_Mensagem",
                "result": {"success": False},
            }
        ]
        assert should_post_chatbot_reply("Falhou o envio", tool_calls) == "Falhou o envio"

    def test_none_tool_calls_treated_as_empty_list(self):
        assert should_post_chatbot_reply("Olá!", None) == "Olá!"


@pytest.mark.unit
class TestSplitDiscordMessage:
    def test_short_message_returns_single_chunk(self):
        text = "Hello, world!"
        assert split_discord_message(text) == [text]

    def test_exact_limit_returns_single_chunk(self):
        text = "a" * DISCORD_MESSAGE_LIMIT
        assert split_discord_message(text) == [text]

    def test_2500_chars_splits_into_two_chunks_preserving_content(self):
        text = "a" * 2500
        chunks = split_discord_message(text)
        assert len(chunks) == 2
        assert "".join(chunks) == text
        assert len(chunks[0]) == DISCORD_MESSAGE_LIMIT
        assert len(chunks[1]) == 500

    def test_splits_on_newline_when_possible(self):
        part_a = "a" * 1999
        part_b = "b" * 500
        text = f"{part_a}\n{part_b}"
        chunks = split_discord_message(text)
        assert len(chunks) == 2
        assert chunks[0] == part_a + "\n"
        assert chunks[1] == part_b
        assert "".join(chunks) == text


@pytest.mark.unit
class TestPostChatbotReply:
    @pytest.mark.asyncio
    async def test_none_channel_skips_send(self):
        await post_chatbot_reply(None, "Hello", [])

    @pytest.mark.asyncio
    async def test_suppressed_response_skips_send(self):
        channel = AsyncMock()
        await post_chatbot_reply(channel, "Ação executada.", [])
        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_chunk_send(self):
        channel = AsyncMock()
        await post_chatbot_reply(channel, "Olá!", [])
        channel.send.assert_awaited_once_with("Olá!")

    @pytest.mark.asyncio
    async def test_multi_chunk_send(self):
        channel = AsyncMock()
        text = "a" * 2500
        await post_chatbot_reply(channel, text, [])
        assert channel.send.await_count == 2
        sent = [call.args[0] for call in channel.send.await_args_list]
        assert "".join(sent) == text

    @pytest.mark.asyncio
    async def test_stops_on_first_chunk_send_failure(self):
        channel = AsyncMock()
        response = MagicMock()
        response.status = 429
        channel.send = AsyncMock(
            side_effect=discord.HTTPException(response, "rate limited")
        )
        text = "a" * 2500
        with patch("features.discord.chatbot_reply.logger") as mock_logger:
            await post_chatbot_reply(channel, text, [])
        assert channel.send.await_count == 1
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception_stops_send_and_logs(self):
        channel = AsyncMock()
        channel.send = AsyncMock(side_effect=RuntimeError("network down"))
        with patch("features.discord.chatbot_reply.logger") as mock_logger:
            await post_chatbot_reply(channel, "Olá!", [])
        channel.send.assert_awaited_once()
        mock_logger.error.assert_called_once()
