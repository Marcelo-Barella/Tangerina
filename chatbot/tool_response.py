from typing import Any, Dict, List, Optional

from features.discord.chatbot_reply import _SUPPRESSED_RESPONSES

def _result_message(result: Dict[str, Any], default: str) -> str:
    message = (result.get("message") or "").strip()
    return message or default


_TERMINAL_TOOL_REPLIES = {
    "EnterChannel": lambda r: f"Pronto, entrei no {r.get('channel_name') or 'canal de voz'}!",
    "LeaveChannel": lambda _: "Saí do canal de voz.",
    "MusicLeave": lambda _: "Saí do canal de voz.",
    "MusicStop": lambda r: _result_message(r, "Música parada."),
    "MusicSkip": lambda r: _result_message(r, "Música pulada."),
    "MusicPause": lambda r: _result_message(r, "Música pausada."),
    "MusicResume": lambda r: _result_message(r, "Música retomada."),
    "MusicVolume": lambda r: _result_message(r, "Volume ajustado."),
}
_SKIP_OVERRIDE_TOOLS = frozenset({
    "MusicPlay", "MusicSpotifyPlay", "SEND_Mensagem", "TTSSpeak",
})


def _tool_failed(result: Dict[str, Any]) -> bool:
    if result.get("success") is False:
        return True
    if result.get("error") and result.get("success") is not True:
        return True
    return False


def _format_music_queue_reply(result: Dict[str, Any]) -> str:
    queue = result.get("queue") or []
    current = result.get("current")
    if not queue and not current:
        return "Fila vazia"
    lines: List[str] = []
    if current:
        lines.append(f"Tocando agora: {current.get('title', 'Unknown')}")
    for index, song in enumerate(queue[:5]):
        lines.append(f"{index + 1}. {song.get('title', 'Unknown')}")
    return f"Fila:\n```{chr(10).join(lines)}```"


def _format_web_search_reply(result: Dict[str, Any]) -> str:
    results = result.get("results") or []
    if not results:
        return "Nenhum resultado encontrado."
    lines: List[str] = []
    for item in results[:5]:
        title = (item.get("title") or "").strip() or "Sem título"
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        block = title
        if url:
            block = f"{title}\n{url}"
        if content:
            block = f"{block}\n{content}"
        lines.append(block)
    return "\n\n".join(lines)


def derive_action_reply(
    tool_calls_executed: List[Dict[str, Any]],
    *,
    for_fallback: bool = False,
) -> Optional[str]:
    if for_fallback:
        for tc in reversed(tool_calls_executed):
            result = tc.get("result") or {}
            if _tool_failed(result):
                return f"Erro ao executar ação: {result.get('error', 'Erro desconhecido')}"
    for tc in reversed(tool_calls_executed):
        tool = tc.get("tool")
        result = tc.get("result") or {}
        if _tool_failed(result):
            continue
        if for_fallback and tool == "GET_MusicQueue":
            return _format_music_queue_reply(result)
        if for_fallback and tool == "WebSearch":
            return _format_web_search_reply(result)
        if tool in _SKIP_OVERRIDE_TOOLS:
            if for_fallback:
                continue
            return None
        replier = _TERMINAL_TOOL_REPLIES.get(tool)
        if replier:
            return replier(result)
    if for_fallback:
        for tc in reversed(tool_calls_executed):
            tool = tc.get("tool")
            result = tc.get("result") or {}
            if tool == "MusicPlay" and not _tool_failed(result):
                return _result_message(result, "Tocando música.")
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
