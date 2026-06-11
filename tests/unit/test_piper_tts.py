import os
from unittest.mock import MagicMock, patch

import pytest

from features.tts.piper_tts import PiperTTS


@pytest.mark.unit
class TestPiperTTS:
    def test_http_mode_delegates_to_http_client(self, tmp_path):
        with patch.dict(os.environ, {"PIPER_API_URL": "http://localhost:5001/"}):
            client = PiperTTS()
            output_path = str(tmp_path / "out.wav")

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [b"RIFF", b"WAVE"]

            with patch("features.tts.http_tts.requests.post", return_value=mock_response):
                result = client.generate_speech("ola", output_path=output_path)

            assert result == output_path
            assert client.use_http is True

    def test_http_mode_strips_trailing_slash(self):
        with patch.dict(os.environ, {"PIPER_API_URL": "http://localhost:5001/"}):
            client = PiperTTS()
            assert client._http_client.api_url == "http://localhost:5001"

    def test_generate_speech_rejects_empty_text(self):
        with patch.dict(os.environ, {"PIPER_API_URL": "http://localhost:5001"}):
            client = PiperTTS()
            with pytest.raises(ValueError, match="non-empty string"):
                client.generate_speech("   ")

    def test_subprocess_mode_raises_on_piper_failure(self, tmp_path):
        env = {"PIPER_API_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPER_API_URL", None)
            client = PiperTTS(model_path="/fake/model.onnx", piper_bin="/usr/bin/piper")

            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.stderr = "model load failed"

            with patch("features.tts.piper_tts.subprocess.run", return_value=mock_process):
                with pytest.raises(RuntimeError, match="model load failed"):
                    client.generate_speech("ola", output_path=str(tmp_path / "out.wav"))

    def test_subprocess_mode_cleans_up_on_failure(self, tmp_path):
        env = {"PIPER_API_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("PIPER_API_URL", None)
            client = PiperTTS(model_path="/fake/model.onnx", piper_bin="/usr/bin/piper")
            output_path = str(tmp_path / "out.wav")

            with patch(
                "features.tts.piper_tts.subprocess.run",
                side_effect=OSError("broken pipe"),
            ):
                with pytest.raises(OSError, match="broken pipe"):
                    client.generate_speech("ola", output_path=output_path)

            assert not os.path.exists(output_path)
