import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from chatbot.tool_response import resolve_tool_response
from chatbot.typesafe_candidates import (
    music_play_query_candidates,
    volume_candidates,
    web_search_query_candidates,
)
from chatbot.typesafe_settings import (
    ROUTE_NONE_LABEL,
    ROUTABLE_TOOLS,
    VOICE_CONVERSATION,
    VOICE_FAST_COMMAND,
    VOICE_IGNORE,
    arg_confidence_min,
    route_confidence_min,
    tts_speak_confidence_min,
    typesafe_enabled,
    typesafe_model,
    voice_noul_confidence_min,
    voice_path_confidence_min,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceTranscriptDecision:
    usable: bool
    path: str
    wake_for_conversation: bool
    use_legacy_routing: bool


@dataclass(frozen=True)
class TtsPlaybackDecision:
    should_speak: bool
    provider: str
    music_duck_level: int
    mixed_volume: float


def _choice_answer(result: Any, key: str) -> Tuple[Optional[str], float]:
    choices = getattr(result, "choices", None) or {}
    answer = choices.get(key)
    if answer is None:
        return None, 0.0
    choice = getattr(answer, "choice", None)
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    return choice, confidence


def _noul_answer(result: Any, key: str) -> Tuple[float, float]:
    nouls = getattr(result, "nouls", None) or {}
    answer = nouls.get(key)
    if answer is None:
        return 0.0, 0.0
    noul = float(getattr(answer, "noul", 0.0) or 0.0)
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    return noul, confidence


def _score_answer(result: Any, key: str) -> Tuple[int, float]:
    scores = getattr(result, "scores", None) or {}
    answer = scores.get(key)
    if answer is None:
        return 0, 0.0
    score = int(getattr(answer, "score", 0) or 0)
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    return score, confidence


def _duck_volume_for_level(level: int) -> float:
    if level >= 2:
        return 0.35
    if level == 1:
        return 0.2
    return 0.05


class TypeSafeToolRouter:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = (api_key or os.getenv("TYPESAFE_API_KEY") or "").strip() or None
        self.enabled = typesafe_enabled() and bool(self._api_key)
        self._model = typesafe_model()

    async def _system_one(self, state: Any, questions: Mapping[str, Any]) -> Any:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient(api_key=self._api_key, model=self._model) as client:
            return await client.system_one(state, dict(questions))

    def _build_tool_route_questions(
        self,
        message: str,
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str], Dict[str, str]]:
        from typesafe_sdk import Choice, Noul

        route_criteria = {ROUTE_NONE_LABEL: "Conversation or unclear intent; no direct tool action."}
        for tool in sorted(ROUTABLE_TOOLS):
            route_criteria[tool] = f"User wants the bot to run {tool}."

        play_criteria = music_play_query_candidates(message)
        volume_criteria = volume_candidates(message)
        search_criteria = web_search_query_candidates(message)

        questions: Dict[str, Any] = {
            "tool_route": Choice(
                instructions=(
                    "Given a Portuguese Discord message to assistant Tangerina, "
                    "pick the single best tool to run immediately, or none."
                ),
                criteria=route_criteria,
            ),
            "needs_voice_channel": Noul(
                instructions="Does the selected action require the user's current voice channel?",
            ),
        }
        if play_criteria:
            questions["music_query_span"] = Choice(
                instructions="If the user asked to play music, pick the best search query span.",
                criteria=play_criteria,
            )
        if volume_criteria:
            questions["volume_choice"] = Choice(
                instructions="If the user asked to change music volume, pick the intended level 0-100.",
                criteria=volume_criteria,
            )
        if search_criteria:
            questions["web_query_span"] = Choice(
                instructions="If the user asked for a web search, pick the best query span.",
                criteria=search_criteria,
            )
        return questions, play_criteria, volume_criteria, search_criteria

    async def try_route_user_turn(
        self,
        chatbot: Any,
        message: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: Optional[int],
        app_functions: Optional[Dict[str, Any]],
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        if not self.enabled or guild_id is None:
            return None
        text = message.strip()
        if not text:
            return None

        try:
            questions, play_map, volume_map, search_map = self._build_tool_route_questions(text)
            result = await self._system_one(text, questions)
        except Exception as exc:
            logger.warning("TypeSafe tool route failed, falling back to LLM: %s", exc)
            return None

        tool_name, route_conf = _choice_answer(result, "tool_route")
        if not tool_name or tool_name == ROUTE_NONE_LABEL:
            return None
        if tool_name not in ROUTABLE_TOOLS:
            return None
        if route_conf < route_confidence_min():
            logger.info(
                "TypeSafe route %s below confidence %.2f < %.2f",
                tool_name,
                route_conf,
                route_confidence_min(),
            )
            return None

        params: Dict[str, Any] = {"guild_id": guild_id}
        if tool_name == "MusicPlay":
            query_key, query_conf = _choice_answer(result, "music_query_span")
            if not query_key or query_key not in play_map or query_conf < arg_confidence_min():
                return None
            voice_channel_id = await self._resolve_voice_channel_id(
                chatbot, app_functions, guild_id, user_id
            )
            if voice_channel_id is None:
                return None
            params["channel_id"] = voice_channel_id
            params["query"] = play_map[query_key]
        elif tool_name == "MusicVolume":
            vol_key, vol_conf = _choice_answer(result, "volume_choice")
            if not vol_key or vol_key not in volume_map or vol_conf < arg_confidence_min():
                return None
            try:
                volume = int(volume_map[vol_key])
            except ValueError:
                return None
            if not 0 <= volume <= 100:
                return None
            params["volume"] = volume
        elif tool_name == "WebSearch":
            search_key, search_conf = _choice_answer(result, "web_query_span")
            if not search_key or search_key not in search_map or search_conf < arg_confidence_min():
                return None
            params["query"] = search_map[search_key]

        tool_result = await chatbot._call_tool(
            tool_name,
            params,
            app_functions or {},
            guild_id,
            channel_id,
            user_id,
        )
        tool_calls_executed = [{"tool": tool_name, "parameters": params, "result": tool_result}]
        if not tool_result.get("success"):
            err = tool_result.get("error", "Erro desconhecido")
            return f"Erro ao executar ação: {err}", tool_calls_executed

        if tool_result.get("message"):
            return str(tool_result["message"]), tool_calls_executed
        return resolve_tool_response(tool_calls_executed), tool_calls_executed

    async def _resolve_voice_channel_id(
        self,
        chatbot: Any,
        app_functions: Optional[Dict[str, Any]],
        guild_id: int,
        user_id: Optional[int],
    ) -> Optional[int]:
        if user_id is None:
            return None
        uvc = await chatbot._call_tool(
            "GET_UserVoiceChannel",
            {"guild_id": guild_id, "user_id": user_id},
            app_functions or {},
            guild_id,
            None,
            user_id,
        )
        if not uvc.get("success") or not uvc.get("in_voice_channel"):
            return None
        channel_id = uvc.get("channel_id")
        return int(channel_id) if channel_id is not None else None

    async def evaluate_voice_transcript(
        self,
        transcript: str,
        *,
        listening_mode: bool,
        wake_word_present: bool,
    ) -> VoiceTranscriptDecision:
        if not self.enabled:
            return VoiceTranscriptDecision(
                usable=True,
                path=VOICE_CONVERSATION if listening_mode or wake_word_present else VOICE_FAST_COMMAND,
                wake_for_conversation=wake_word_present,
                use_legacy_routing=True,
            )

        from typesafe_sdk import Choice, Noul, Score

        state = {
            "transcript": transcript,
            "listening_mode": listening_mode,
            "wake_word_present": wake_word_present,
            "language": "pt-BR",
        }
        questions = {
            "usable_speech": Noul(
                instructions="Is this transcript usable user speech directed at a voice assistant?",
            ),
            "wake_intent": Noul(
                instructions="Is the user invoking the assistant by name or starting a conversation?",
            ),
            "transcript_quality": Score(
                instructions="How clear and complete is this transcript?",
                criteria=["unusable", "partial", "clear"],
            ),
            "voice_path": Choice(
                instructions=(
                    "Route this post-STT transcript: fast_command for direct music/control commands, "
                    "conversation for assistant chat, ignore for noise or unrelated speech."
                ),
                criteria={
                    VOICE_FAST_COMMAND: "Direct bot control (music, volume, queue, leave).",
                    VOICE_CONVERSATION: "Open conversation with the assistant.",
                    VOICE_IGNORE: "Not actionable; background noise or unrelated.",
                },
            ),
        }
        try:
            result = await self._system_one(state, questions)
        except Exception as exc:
            logger.warning("TypeSafe voice gate failed, legacy routing: %s", exc)
            return VoiceTranscriptDecision(
                usable=True,
                path=VOICE_CONVERSATION if listening_mode or wake_word_present else VOICE_FAST_COMMAND,
                wake_for_conversation=wake_word_present,
                use_legacy_routing=True,
            )

        usable_prob, usable_conf = _noul_answer(result, "usable_speech")
        path, path_conf = _choice_answer(result, "voice_path")
        wake_prob, wake_conf = _noul_answer(result, "wake_intent")
        quality_score, quality_conf = _score_answer(result, "transcript_quality")

        if usable_conf >= voice_noul_confidence_min() and usable_prob < 0.5:
            return VoiceTranscriptDecision(
                usable=False,
                path=VOICE_IGNORE,
                wake_for_conversation=False,
                use_legacy_routing=False,
            )

        if quality_conf >= voice_noul_confidence_min() and quality_score == 0:
            return VoiceTranscriptDecision(
                usable=False,
                path=VOICE_IGNORE,
                wake_for_conversation=False,
                use_legacy_routing=False,
            )

        if not path or path_conf < voice_path_confidence_min():
            return VoiceTranscriptDecision(
                usable=True,
                path=VOICE_CONVERSATION if listening_mode or wake_word_present else VOICE_FAST_COMMAND,
                wake_for_conversation=wake_word_present,
                use_legacy_routing=True,
            )

        wake_for_conversation = wake_word_present
        if wake_conf >= voice_noul_confidence_min() and wake_prob >= 0.5:
            wake_for_conversation = True

        return VoiceTranscriptDecision(
            usable=True,
            path=path,
            wake_for_conversation=wake_for_conversation,
            use_legacy_routing=False,
        )

    async def evaluate_tts_playback(
        self,
        response_text: str,
        available_providers: List[str],
        *,
        music_playing: bool,
        default_provider: str,
    ) -> TtsPlaybackDecision:
        fallback = TtsPlaybackDecision(
            should_speak=True,
            provider=default_provider if default_provider in available_providers else (available_providers[0] if available_providers else default_provider),
            music_duck_level=1 if music_playing else 0,
            mixed_volume=_duck_volume_for_level(1 if music_playing else 0),
        )
        if not self.enabled or not response_text.strip() or not available_providers:
            return fallback

        from typesafe_sdk import Choice, Noul, Score

        provider_criteria = {name: None for name in available_providers}
        questions = {
            "should_speak": Noul(
                instructions="Should the assistant read this reply aloud to the user in voice?",
            ),
            "tts_provider": Choice(
                instructions="Pick the best TTS provider for this reply.",
                criteria=provider_criteria,
            ),
            "music_duck": Score(
                instructions="How much should background music duck while speaking?",
                criteria=["none", "light", "heavy"],
            ),
        }
        state = {"reply_text": response_text.strip(), "music_playing": music_playing}
        try:
            result = await self._system_one(state, questions)
        except Exception as exc:
            logger.warning("TypeSafe TTS gate failed, default playback: %s", exc)
            return fallback

        speak_prob, speak_conf = _noul_answer(result, "should_speak")
        if speak_conf >= tts_speak_confidence_min() and speak_prob < 0.5:
            return TtsPlaybackDecision(
                should_speak=False,
                provider=fallback.provider,
                music_duck_level=0,
                mixed_volume=_duck_volume_for_level(0),
            )

        provider, provider_conf = _choice_answer(result, "tts_provider")
        if not provider or provider not in available_providers or provider_conf < arg_confidence_min():
            provider = fallback.provider

        duck_level, duck_conf = _score_answer(result, "music_duck")
        if duck_conf < arg_confidence_min():
            duck_level = fallback.music_duck_level
        if not music_playing:
            duck_level = 0

        return TtsPlaybackDecision(
            should_speak=True,
            provider=provider,
            music_duck_level=duck_level,
            mixed_volume=_duck_volume_for_level(duck_level),
        )
