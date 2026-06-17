import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000

_SUPPRESSED_RESPONSES = frozenset({
    "Ação executada.",
    "Ação executada com sucesso!",
})


def split_discord_message(text: str) -> list[str]:
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + DISCORD_MESSAGE_LIMIT
        if end >= len(text):
            chunks.append(text[start:])
            break
        window = text[start:end]
        newline_pos = window.rfind("\n")
        if newline_pos > 0:
            cut = start + newline_pos + 1
        else:
            cut = end
        chunks.append(text[start:cut])
        start = cut
    return chunks


def _bot_role_mentioned(message: Any) -> bool:
    guild = getattr(message, "guild", None)
    if guild is None:
        return False
    me = getattr(guild, "me", None)
    if me is None:
        return False
    mentioned_role_ids = {role.id for role in getattr(message, "role_mentions", [])}
    if not mentioned_role_ids:
        return False
    return any(role.id in mentioned_role_ids for role in me.roles)


def should_respond_with_chatbot(message: Any, bot_user: Any = None) -> bool:
    if message.author.bot:
        return False
    content = (message.content or "").lower().strip()
    return (
        "tangerina" in content
        or (bot_user and bot_user.mentioned_in(message))
        or _bot_role_mentioned(message)
        or message.guild is None
    )


def should_post_chatbot_reply(
    response: Any,
    tool_calls: Optional[list[dict[str, Any]]],
) -> bool:
    if not isinstance(response, str):
        return False
    normalized = response.strip()
    if not normalized:
        return False
    if normalized in _SUPPRESSED_RESPONSES:
        return False
    sent_texts: list[str] = []
    for tc in tool_calls or []:
        if tc.get("tool") != "SEND_Mensagem":
            continue
        if tc.get("result", {}).get("success") is not True:
            continue
        text = tc.get("parameters", {}).get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if stripped:
            sent_texts.append(stripped)
    if sent_texts and normalized in sent_texts:
        return False
    return True


async def post_chatbot_reply(
    channel: Any,
    response: Any,
    tool_calls: Optional[list[dict[str, Any]]],
) -> None:
    if channel is None:
        return
    if not should_post_chatbot_reply(response, tool_calls):
        return
    text = response.strip()
    for chunk in split_discord_message(text):
        try:
            await channel.send(chunk)
        except Exception as e:
            logger.error(f"Error sending chatbot reply: {e}")
            return
