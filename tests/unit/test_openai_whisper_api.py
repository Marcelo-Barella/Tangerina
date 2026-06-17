from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from features.voice.openai_whisper_api import (
    WHISPER_API_MODEL,
    transcribe_openai_whisper,
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
