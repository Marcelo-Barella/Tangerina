from unittest.mock import MagicMock, patch

import pytest

from features.tts.http_tts import HttpTTSClient


@pytest.mark.unit
class TestOmnivoiceHttpTTSClient:
    def test_init_requires_api_url(self):
        with pytest.raises(RuntimeError, match="OmniVoice API URL is required"):
            HttpTTSClient("", 90, "OmniVoice")

    def test_init_strips_trailing_slash(self):
        client = HttpTTSClient("http://localhost:5003/", 90, "OmniVoice")
        assert client.api_url == "http://localhost:5003"

    def test_generate_speech_rejects_empty_text(self):
        client = HttpTTSClient("http://localhost:5003", 90, "OmniVoice")
        with pytest.raises(ValueError, match="non-empty string"):
            client.generate_speech("   ")

    def test_generate_speech_writes_response(self, tmp_path):
        client = HttpTTSClient("http://localhost:5003", 90, "OmniVoice")
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
        client = HttpTTSClient("http://localhost:5003", 90, "OmniVoice")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "model not loaded"}

        with patch("features.tts.http_tts.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="OmniVoice TTS API error"):
                client.generate_speech("ola")
