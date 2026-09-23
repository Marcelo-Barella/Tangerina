import logging
import os
import re
import wave
from io import BytesIO
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SHORT_CLIP_PROMPT_MAX_SEC = float(os.getenv("WHISPER_SHORT_CLIP_MAX_SEC", "2.5"))
LONG_CLIP_PROMPT_MIN_SEC = float(os.getenv("WHISPER_LONG_CLIP_MIN_SEC", "4.0"))
SHORT_WHISPER_PROMPT = os.getenv(
    "WHISPER_SHORT_INITIAL_PROMPT",
    "Transcreva em português brasileiro.",
)
WHISPER_INITIAL_PROMPT = os.getenv(
    "WHISPER_INITIAL_PROMPT",
    (
        "Transcreva em português brasileiro. Comandos de voz para o assistente musical Tangerina: "
        "toca a música, para a música, pula a música, pausa a música, continua a música, "
        "fila de música, volume, tangerina."
    ),
)
PROMPT_HALLUCINATION_OVERLAP = float(os.getenv("WHISPER_PROMPT_OVERLAP_REJECT", "0.55"))

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

_HALLUCINATION_PHRASES = (
    "comandos de voz",
    "fila de música",
    "fila de musica",
    "assistenter musical",
    "assistenter",
    "assistente musical",
)

_BOILERPLATE_WORDS = frozenset(
    {
        "comandos",
        "assistente",
        "assistenter",
        "musical",
        "transcreva",
        "português",
        "portugues",
        "brasileiro",
    }
)


def wav_duration_seconds(wav_buffer: BytesIO) -> float:
    wav_buffer.seek(0)
    with wave.open(wav_buffer, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate() or 1
        return frames / float(rate)


def pcm_duration_seconds(
    pcm_bytes: int,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> float:
    if sample_rate <= 0 or sample_width <= 0 or channels <= 0:
        return 0.0
    bytes_per_second = sample_rate * sample_width * channels
    return pcm_bytes / float(bytes_per_second)


def compute_clip_metrics(
    pcm_mono: bytes,
    wav_buffer: BytesIO,
    *,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> Dict[str, Any]:
    wav_buffer.seek(0)
    wav_bytes = wav_buffer.getvalue()
    duration_sec = pcm_duration_seconds(
        len(pcm_mono), sample_rate, sample_width, channels
    )
    rms: Optional[int] = None
    try:
        import audioop

        rms = audioop.rms(pcm_mono, sample_width)
    except (ImportError, AttributeError):
        pass
    return {
        "duration_sec": duration_sec,
        "rms": rms,
        "wav_bytes": len(wav_bytes),
        "pcm_bytes": len(pcm_mono),
    }


def log_clip_metrics(metrics: Dict[str, Any], *, guild_id: Optional[int] = None) -> None:
    prefix = f"guild={guild_id} " if guild_id is not None else ""
    logger.info(
        "%sSTT clip metrics: duration=%.2fs rms=%s wav_bytes=%s pcm_bytes=%s",
        prefix,
        metrics.get("duration_sec", 0.0),
        metrics.get("rms"),
        metrics.get("wav_bytes"),
        metrics.get("pcm_bytes"),
    )


def select_whisper_prompt(full_prompt: str, duration_sec: float) -> str:
    full = (full_prompt or "").strip()
    if not full:
        return ""
    if duration_sec <= 0:
        return SHORT_WHISPER_PROMPT
    if duration_sec < SHORT_CLIP_PROMPT_MAX_SEC:
        return SHORT_WHISPER_PROMPT
    if duration_sec < LONG_CLIP_PROMPT_MIN_SEC:
        first_sentence = full.split(".")[0].strip()
        return first_sentence + "." if first_sentence else SHORT_WHISPER_PROMPT
    return full


def is_prompt_hallucination(text: str, full_prompt: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _CJK_RE.search(cleaned):
        return True
    lower = cleaned.lower()
    words = _WORD_RE.findall(lower)
    if any(phrase in lower for phrase in _HALLUCINATION_PHRASES):
        if len(words) <= 12:
            return True
    if len(words) < 2:
        return False
    word_set = set(words)
    boilerplate_hits = word_set & _BOILERPLATE_WORDS
    if (
        len(boilerplate_hits) >= 2
        and len(boilerplate_hits) / len(word_set) >= PROMPT_HALLUCINATION_OVERLAP
        and "tangerina" not in word_set
    ):
        return True
    collapsed_text = re.sub(r"\s+", " ", lower)
    collapsed_prompt = re.sub(r"\s+", " ", (full_prompt or "").lower())
    if (
        collapsed_prompt
        and len(collapsed_text) >= 24
        and collapsed_text in collapsed_prompt
    ):
        return True
    return False


def filter_transcript(text: Optional[str], full_prompt: str) -> Optional[str]:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if is_prompt_hallucination(stripped, full_prompt):
        logger.warning("Rejected prompt-shaped STT transcript: %r", stripped)
        return None
    return stripped
