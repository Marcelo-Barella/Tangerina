import os
from typing import BinaryIO, Optional

WHISPER_API_MODEL = "whisper-1"


def whisper_transcription_timeout() -> float:
    return float(os.getenv("WHISPER_TRANSCRIPTION_TIMEOUT", "30"))


TRANSCRIPTION_TIMEOUT = whisper_transcription_timeout()
DEFAULT_WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")


def build_openai_whisper_client(api_key: str, timeout: float = TRANSCRIPTION_TIMEOUT):
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout)


def transcribe_openai_whisper(
    client,
    audio_file: BinaryIO,
    *,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    kwargs = {"model": WHISPER_API_MODEL, "file": audio_file}
    if language:
        kwargs["language"] = language
    if prompt:
        kwargs["prompt"] = prompt
    result = client.audio.transcriptions.create(**kwargs)
    return (result.text or "").strip()
