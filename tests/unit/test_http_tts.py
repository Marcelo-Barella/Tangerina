import os
from unittest.mock import MagicMock, patch

import pytest

from features.tts.http_tts import create_omnivoice_client


@pytest.mark.unit
class TestHttpTTS:
    def test_init_requires_api_url(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OMNIVOICE_API_URL"):
                create_omnivoice_client()

    def test_init_strips_trailing_slash(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003/"}):
            client = create_omnivoice_client()
            assert client.api_url == "http://localhost:5003"

    def test_generate_speech_rejects_empty_text(self):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()
            with pytest.raises(ValueError, match="non-empty string"):
                client.generate_speech("   ")

    def test_generate_speech_writes_response(self, tmp_path):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()
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
            client = create_omnivoice_client()

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "model not loaded"}

            with patch("features.tts.http_tts.requests.post", return_value=mock_response):
                with pytest.raises(RuntimeError, match="OmniVoice TTS API error"):
                    client.generate_speech("ola")

    def test_generate_speech_raises_on_timeout(self):
        import requests

        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()

            with patch(
                "features.tts.http_tts.requests.post",
                side_effect=requests.exceptions.Timeout(),
            ):
                with pytest.raises(RuntimeError, match="TTS generation timed out"):
                    client.generate_speech("ola")

    def test_generate_speech_raises_on_connection_error(self):
        import requests

        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()

            with patch(
                "features.tts.http_tts.requests.post",
                side_effect=requests.exceptions.ConnectionError("refused"),
            ):
                with pytest.raises(RuntimeError, match="Failed to connect to OmniVoice"):
                    client.generate_speech("ola")

    def test_generate_speech_raises_on_empty_response(self, tmp_path):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()
            output_path = str(tmp_path / "out.wav")

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = []

            with patch("features.tts.http_tts.requests.post", return_value=mock_response):
                with pytest.raises(RuntimeError, match="empty or invalid audio file"):
                    client.generate_speech("ola", output_path=output_path)

    def test_generate_speech_cleans_up_on_write_failure(self, tmp_path):
        with patch.dict(os.environ, {"OMNIVOICE_API_URL": "http://localhost:5003"}):
            client = create_omnivoice_client()
            output_path = str(tmp_path / "out.wav")

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"RIFF"]

            with (
                patch("features.tts.http_tts.requests.post", return_value=mock_response),
                patch("builtins.open", side_effect=OSError("disk full")),
                patch("features.tts.http_tts.cleanup_tts_file") as cleanup,
            ):
                with pytest.raises(OSError, match="disk full"):
                    client.generate_speech("ola", output_path=output_path)

            cleanup.assert_called_once_with(output_path)

    def test_ensure_output_path_creates_temp_file_when_missing(self):
        from features.tts.http_tts import ensure_output_path

        path = ensure_output_path(None)
        try:
            assert path.endswith(".wav")
            assert os.path.exists(path)
        finally:
            os.remove(path)

    def test_cleanup_tts_file_removes_existing_file(self, tmp_path):
        from features.tts.http_tts import cleanup_tts_file

        audio_file = tmp_path / "speech.wav"
        audio_file.write_bytes(b"RIFF")
        cleanup_tts_file(str(audio_file))
        assert not audio_file.exists()
