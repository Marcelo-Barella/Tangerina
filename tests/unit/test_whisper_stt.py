import io
import struct
import wave

import pytest

from features.voice import whisper_stt
from features.voice.whisper_stt import WHISPER_INITIAL_PROMPT


def _make_wav(duration_sec: float, sample_rate: int = 48000) -> io.BytesIO:
    frames = int(duration_sec * sample_rate)
    pcm = struct.pack("<h", 12000) * frames
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    buf.seek(0)
    return buf


@pytest.mark.unit
class TestWhisperPromptSelection:
    def test_short_clip_uses_brief_prompt(self):
        prompt = whisper_stt.select_whisper_prompt(WHISPER_INITIAL_PROMPT, 1.0)
        assert prompt == whisper_stt.SHORT_WHISPER_PROMPT
        assert "fila de música" not in prompt

    def test_long_clip_uses_full_prompt(self):
        prompt = whisper_stt.select_whisper_prompt(WHISPER_INITIAL_PROMPT, 5.0)
        assert prompt == WHISPER_INITIAL_PROMPT


@pytest.mark.unit
class TestPromptHallucinationFilter:
    def test_rejects_prompt_fragment_transcript(self):
        text = "comandos de voz fila de música volume"
        assert whisper_stt.is_prompt_hallucination(text, WHISPER_INITIAL_PROMPT)

    def test_rejects_cjk_junk(self):
        assert whisper_stt.is_prompt_hallucination("你好世界", WHISPER_INITIAL_PROMPT)

    def test_keeps_wake_word_utterance(self):
        text = "olá tangerina toca música"
        assert not whisper_stt.is_prompt_hallucination(text, WHISPER_INITIAL_PROMPT)

    def test_filter_transcript_returns_none_for_hallucination(self):
        assert whisper_stt.filter_transcript("comandos de voz", WHISPER_INITIAL_PROMPT) is None


@pytest.mark.unit
class TestClipMetrics:
    def test_compute_clip_metrics(self):
        wav = _make_wav(1.0)
        pcm = b"\xff\x7f" * 48000
        metrics = whisper_stt.compute_clip_metrics(
            pcm,
            wav,
            sample_rate=48000,
            sample_width=2,
            channels=1,
        )
        assert metrics["duration_sec"] == pytest.approx(1.0, rel=0.05)
        assert metrics["wav_bytes"] > 0
        assert metrics["rms"] is not None
