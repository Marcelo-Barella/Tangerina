import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from features.voice.openai_whisper_api import (
    WHISPER_API_MODEL,
    transcribe_openai_whisper,
    whisper_transcription_timeout,
)


@pytest.mark.unit
class TestOpenaiWhisperApi:
    def test_transcribe_builds_expected_request(self):
        client = MagicMock()
        client.audio.transcriptions.create.return_value = MagicMock(text="  oi  ")
        audio = BytesIO(b"wav-bytes")

        text = transcribe_openai_whisper(
            client,
            audio,
            language="pt",
            prompt="comandos de voz",
        )

        assert text == "oi"
        client.audio.transcriptions.create.assert_called_once_with(
            model=WHISPER_API_MODEL,
            file=audio,
            language="pt",
            prompt="comandos de voz",
        )

    def test_transcribe_omits_optional_fields_when_empty(self):
        client = MagicMock()
        client.audio.transcriptions.create.return_value = MagicMock(text="ok")
        audio = BytesIO(b"wav-bytes")

        transcribe_openai_whisper(client, audio)

        client.audio.transcriptions.create.assert_called_once_with(
            model=WHISPER_API_MODEL,
            file=audio,
        )

    def test_whisper_transcription_timeout_defaults_to_30(self):
        with patch.dict(os.environ):
            os.environ.pop("WHISPER_TRANSCRIPTION_TIMEOUT", None)
            assert whisper_transcription_timeout() == 30.0

    def test_whisper_transcription_timeout_reads_env_at_call_time(self):
        with patch.dict(os.environ, {"WHISPER_TRANSCRIPTION_TIMEOUT": "45"}):
            first = whisper_transcription_timeout()
        with patch.dict(os.environ, {"WHISPER_TRANSCRIPTION_TIMEOUT": "12.5"}):
            second = whisper_transcription_timeout()
        assert first == 45.0
        assert second == 12.5

    def test_whisper_transcription_timeout_rejects_invalid_env(self):
        with patch.dict(os.environ, {"WHISPER_TRANSCRIPTION_TIMEOUT": "abc"}):
            with pytest.raises(ValueError):
                whisper_transcription_timeout()
