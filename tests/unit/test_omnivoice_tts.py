import os
from unittest.mock import MagicMock, patch

import pytest

from features.tts.omnivoice_tts import OmnivoiceTTS


@pytest.mark.unit
class TestOmnivoiceTTS:
    def test_init_requires_api_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OMNIVOICE_API_URL"):
                OmnivoiceTTS()

    def test_init_strips_trailing_slash(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003/"}):
            client = OmnivoiceTTS()
            assert client.api_url == "http://localhost:5003"

    def test_generate_speech_rejects_empty_text(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = OmnivoiceTTS()
            with pytest.raises(ValueError, match="non-empty string"):
                client.generate_speech("   ")

    def test_generate_speech_writes_response(self, tmp_path):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = OmnivoiceTTS()
            output_path = str(tmp_path / "out.wav")

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"RIFF", b"WAVE"]

            with patch("features.tts.http_tts.requests.post", return_value=mock_response):
                result = client.generate_speech("ola", output_path=output_path)

            assert result == output_path
            with open(output_path, "rb") as handle:
                assert handle.read() == b"RIFFWAVE"

    def test_generate_speech_raises_on_api_error(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = OmnivoiceTTS()

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "model not loaded"}

            with patch("features.tts.http_tts.requests.post", return_value=mock_response):
                with pytest.raises(RuntimeError, match="OmniVoice TTS API error"):
                    client.generate_speech("ola")
