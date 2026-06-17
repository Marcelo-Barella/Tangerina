from typing import Any, Dict, List, Optional

from features.discord.chatbot_reply import _SUPPRESSED_RESPONSES

_TERMINAL_TOOL_REPLIES = {
    "EnterChannel": lambda r: f"Pronto, entrei no {r.get('channel_name') or 'canal de voz'}!",
    "LeaveChannel": lambda _: "Saí do canal de voz.",
    "MusicLeave": lambda _: "Saí do canal de voz.",
}
_SKIP_OVERRIDE_TOOLS = frozenset({
    "MusicPlay", "MusicSpotifyPlay", "SEND_Mensagem", "TTSSpeak",
})


def derive_action_reply(
    tool_calls_executed: List[Dict[str, Any]],
    *,
    for_fallback: bool = False,
) -> Optional[str]:
    if for_fallback:
        for tc in reversed(tool_calls_executed):
            result = tc.get("result") or {}
            if not result.get("success"):
                return f"Erro ao executar ação: {result.get('error', 'Erro desconhecido')}"
    for tc in reversed(tool_calls_executed):
        tool = tc.get("tool")
        result = tc.get("result") or {}
        if not result.get("success"):
            continue
        if tool in _SKIP_OVERRIDE_TOOLS:
            if for_fallback:
                continue
            return None
        replier = _TERMINAL_TOOL_REPLIES.get(tool)
        if replier:
            return replier(result)
    return None


def resolve_tool_response(
    tool_calls_executed: List[Dict[str, Any]],
    content: Optional[str] = None,
    send_mensagem_executed: bool = False,
) -> str:
    stripped_content = (content or "").strip() if content is not None else ""
    for_fallback = (
        content is None
        or not stripped_content
        or stripped_content in _SUPPRESSED_RESPONSES
    )
    action_reply = derive_action_reply(
        tool_calls_executed,
        for_fallback=for_fallback,
    )
    if action_reply:
        return action_reply
    if content is not None:
        return (content or "").strip()
    if send_mensagem_executed:
        return ""
    return "Ação executada."
