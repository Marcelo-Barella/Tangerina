import importlib.util
import os
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WHISPER_SERVER_PATH = REPO_ROOT / "deploy" / "whisper" / "server.py"


def _load_whisper_server(env: dict):
    for key in list(sys.modules):
        if key in ("whisper_server", "server") or key.startswith("whisper_server."):
            del sys.modules[key]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    with patch.dict(os.environ, env, clear=True):
        spec = importlib.util.spec_from_file_location("whisper_server", WHISPER_SERVER_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _cleanup_whisper_server_import():
    yield
    for key in list(sys.modules):
        if key in ("whisper_server", "server") or key.startswith("whisper_server."):
            del sys.modules[key]


@pytest.mark.unit
class TestWhisperServerHealth:
    def test_health_reports_openai_api_when_key_set(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "sk-test"})
        client = module.app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok", "provider": "openai-api"}

    def test_health_reports_local_without_key(self):
        module = _load_whisper_server({})
        with patch.object(module, "whisper", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok", "provider": "local"}

    def test_health_503_when_no_backend(self):
        module = _load_whisper_server({})
        with patch.object(module, "whisper", None):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 503


@pytest.mark.unit
class TestWhisperServerTranscribe:
    def test_transcribe_requires_file(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "sk-test"})
        client = module.app.test_client()
        response = client.post("/transcribe")
        assert response.status_code == 400
        assert response.get_json()["error"] == "Missing 'file' upload"

    def test_transcribe_uses_openai_api_when_key_set(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "sk-test"})
        mock_client = MagicMock()
        with patch.object(module, "transcribe_openai_whisper", return_value="toca música") as transcribe:
            with patch.object(module, "_get_openai_client", return_value=mock_client):
                client = module.app.test_client()
                response = client.post(
                    "/transcribe",
                    data={
                        "file": (BytesIO(b"RIFF"), "audio.wav"),
                        "prompt": "test prompt",
                    },
                    content_type="multipart/form-data",
                )
        assert response.status_code == 200
        assert response.get_json() == {"text": "toca música"}
        transcribe.assert_called_once()
        _args, kwargs = transcribe.call_args
        assert kwargs["language"] == "pt"
        assert kwargs["prompt"] == "test prompt"

    def test_transcribe_falls_back_to_local_without_key(self):
        module = _load_whisper_server({})
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "local text"}
        with patch.object(module, "_load_local_model", return_value=mock_model):
            client = module.app.test_client()
            response = client.post(
                "/transcribe",
                data={"file": (BytesIO(b"RIFF"), "audio.wav")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert response.get_json() == {"text": "local text"}

    def test_transcribe_ignores_blank_api_key(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "   "})
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "local text"}
        with patch.object(module, "whisper", MagicMock()):
            with patch.object(module, "_load_local_model", return_value=mock_model):
                client = module.app.test_client()
                response = client.get("/health")
        assert response.get_json()["provider"] == "local"
