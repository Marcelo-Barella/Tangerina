import os
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from features.tts.http_tts import (
    HttpTTSClient,
    cleanup_tts_file,
    create_omnivoice_client,
    ensure_output_path,
)


@pytest.mark.unit
class TestCreateOmnivoiceClient:
    def test_init_requires_api_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OMNIVOICE_API_URL"):
                create_omnivoice_client()

    def test_init_strips_trailing_slash(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003/"}):
            client = create_omnivoice_client()
            assert client.api_url == "http://localhost:5003"


@pytest.mark.unit
class TestHttpTTSClient:
    def test_generate_speech_rejects_empty_text(self):
        client = HttpTTSClient("http://localhost:5003", 30, "OmniVoice")
        with pytest.raises(ValueError, match="non-empty string"):
            client.generate_speech("   ")

    def test_generate_speech_writes_response(self, tmp_path):
        client = HttpTTSClient("http://localhost:5003", 30, "OmniVoice")
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
        client = HttpTTSClient("http://localhost:5003", 30, "OmniVoice")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "model not loaded"}

        with patch("features.tts.http_tts.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="OmniVoice TTS API error"):
                client.generate_speech("ola")

    def test_http_client_rejects_empty_api_url(self):
        with pytest.raises(RuntimeError, match="API URL is required"):
            HttpTTSClient("", 30, "TestProvider")

    def test_generate_speech_requires_requests_library(self):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        with patch("features.tts.http_tts.requests", None):
            with pytest.raises(RuntimeError, match="requests library is required"):
                client.generate_speech("ola")

    def test_generate_speech_raises_on_non_json_api_error(self):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "bad gateway"

        with patch("features.tts.http_tts.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="HTTP 502: bad gateway"):
                client.generate_speech("ola")

    def test_generate_speech_raises_on_empty_audio_response(self, tmp_path):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        output_path = str(tmp_path / "empty.wav")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = []

        with patch("features.tts.http_tts.requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="empty or invalid audio file"):
                client.generate_speech("ola", output_path=output_path)

    def test_generate_speech_raises_on_timeout(self):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        with patch(
            "features.tts.http_tts.requests.post",
            side_effect=requests_lib.exceptions.Timeout("timed out"),
        ):
            with pytest.raises(RuntimeError, match="TTS generation timed out"):
                client.generate_speech("ola")

    def test_generate_speech_raises_on_connection_error(self):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        with patch(
            "features.tts.http_tts.requests.post",
            side_effect=requests_lib.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(RuntimeError, match="Failed to connect to TestProvider"):
                client.generate_speech("ola")

    def test_generate_speech_raises_on_request_exception(self):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        with patch(
            "features.tts.http_tts.requests.post",
            side_effect=requests_lib.exceptions.RequestException("network down"),
        ):
            with pytest.raises(RuntimeError, match="TestProvider TTS API request failed"):
                client.generate_speech("ola")

    def test_generate_speech_cleans_up_on_write_failure(self, tmp_path):
        client = HttpTTSClient("http://localhost:5003", 30, "TestProvider")
        output_path = str(tmp_path / "out.wav")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.side_effect = OSError("disk full")

        with patch("features.tts.http_tts.requests.post", return_value=mock_response):
            with pytest.raises(OSError, match="disk full"):
                client.generate_speech("ola", output_path=output_path)

        assert not os.path.exists(output_path)


@pytest.mark.unit
class TestHttpTTSHelpers:
    def test_ensure_output_path_returns_provided_path(self, tmp_path):
        output_path = str(tmp_path / "custom.wav")
        assert ensure_output_path(output_path) == output_path

    def test_ensure_output_path_creates_temp_file_when_missing(self):
        path = ensure_output_path(None)
        try:
            assert path.endswith(".wav")
            assert os.path.exists(path)
        finally:
            cleanup_tts_file(path)

    def test_cleanup_tts_file_removes_existing_file(self, tmp_path):
        output_path = tmp_path / "cleanup.wav"
        output_path.write_bytes(b"RIFF")
        cleanup_tts_file(str(output_path))
        assert not output_path.exists()

    def test_cleanup_tts_file_ignores_missing_file(self, tmp_path):
        cleanup_tts_file(str(tmp_path / "missing.wav"))

    def test_cleanup_tts_file_swallows_os_error(self, tmp_path):
        output_path = tmp_path / "locked.wav"
        output_path.write_bytes(b"RIFF")
        with patch("features.tts.http_tts.os.remove", side_effect=OSError("permission denied")):
            cleanup_tts_file(str(output_path))
