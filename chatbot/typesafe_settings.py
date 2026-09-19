import os
from typing import FrozenSet, Optional

ROUTABLE_TOOLS: FrozenSet[str] = frozenset(
    {
        "MusicPlay",
        "MusicStop",
        "MusicSkip",
        "MusicPause",
        "MusicResume",
        "MusicVolume",
        "GET_MusicQueue",
        "MusicLeave",
        "WebSearch",
    }
)

ROUTE_NONE_LABEL = "none"

VOICE_FAST_COMMAND = "fast_command"
VOICE_CONVERSATION = "conversation"
VOICE_IGNORE = "ignore"

MUSIC_COMMAND_KEYWORDS = (
    "toca",
    "play",
    "tocar",
    "para",
    "stop",
    "parar",
    "pula",
    "skip",
    "pular",
    "pausa",
    "pause",
    "pausar",
    "continua",
    "resume",
    "continuar",
    "fila",
    "queue",
    "volume",
    "sai",
    "leave",
    "sair",
)


def _float_env(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def typesafe_enabled() -> bool:
    key = os.getenv("TYPESAFE_API_KEY")
    if not key or not key.strip():
        return False
    return os.getenv("TYPESAFE_ENABLED", "true").lower() == "true"


def route_confidence_min() -> float:
    return _float_env("TYPESAFE_ROUTE_CONFIDENCE", "0.65")


def arg_confidence_min() -> float:
    return _float_env("TYPESAFE_ARG_CONFIDENCE", "0.6")


def voice_path_confidence_min() -> float:
    return _float_env("TYPESAFE_VOICE_PATH_CONFIDENCE", "0.6")


def voice_noul_confidence_min() -> float:
    return _float_env("TYPESAFE_VOICE_NOUL_CONFIDENCE", "0.55")


def tts_speak_confidence_min() -> float:
    return _float_env("TYPESAFE_TTS_SPEAK_CONFIDENCE", "0.55")


def typesafe_model() -> Optional[str]:
    model = os.getenv("TYPESAFE_DEFAULT_MODEL")
    if model and model.strip():
        return model.strip()
    return None
