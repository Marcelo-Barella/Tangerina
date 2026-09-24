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

    def test_health_reports_faster_whisper_by_default(self):
        module = _load_whisper_server({})
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok", "provider": "faster-whisper"}

    def test_health_reports_openai_whisper_when_selected(self):
        module = _load_whisper_server({"WHISPER_LOCAL_ENGINE": "openai-whisper"})
        with patch.object(module, "whisper", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok", "provider": "openai-whisper"}

    def test_health_503_when_no_backend(self):
        module = _load_whisper_server({})
        with patch.object(module, "FasterWhisperModel", None), patch.object(module, "whisper", None):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 503


@pytest.mark.unit
class TestWhisperServerReady:
    def test_ready_openai_api_mode(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "sk-test"})
        client = module.app.test_client()
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.get_json() == {
            "state": "ready",
            "provider": "openai-api",
            "model_loaded": True,
        }

    def test_ready_cold_local_without_warm(self):
        module = _load_whisper_server({})
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            client = module.app.test_client()
            response = client.get("/ready")
        assert response.status_code == 503
        body = response.get_json()
        assert body["state"] == "cold"
        assert body["model_loaded"] is False
        assert body["provider"] == "faster-whisper"

    def test_ready_warm_loads_local_model(self):
        module = _load_whisper_server({})
        mock_model = MagicMock()
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            with patch.object(module, "_load_local_model", return_value=mock_model):
                client = module.app.test_client()
                response = client.get("/ready?warm=1")
        assert response.status_code == 200
        body = response.get_json()
        assert body["state"] == "ready"
        assert body["model_loaded"] is True
        assert body["provider"] == "faster-whisper"
        assert body["load_ms"] is not None

    def test_ready_warm_error(self):
        module = _load_whisper_server({})
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            with patch.object(module, "_load_local_model", side_effect=RuntimeError("boom")):
                client = module.app.test_client()
                response = client.get("/ready?warm=1")
        assert response.status_code == 503
        body = response.get_json()
        assert body["state"] == "error"
        assert body["last_error"] == "boom"

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

    def test_transcribe_uses_faster_whisper_without_key(self):
        module = _load_whisper_server({})
        mock_model = MagicMock()
        with patch.object(module, "_load_local_model", return_value=mock_model):
            with patch.object(module, "_transcribe_faster_whisper", return_value="local text") as transcribe:
                client = module.app.test_client()
                response = client.post(
                    "/transcribe",
                    data={"file": (BytesIO(b"RIFF"), "audio.wav")},
                    content_type="multipart/form-data",
                )
        assert response.status_code == 200
        assert response.get_json() == {"text": "local text"}
        transcribe.assert_called_once()

    def test_transcribe_uses_openai_whisper_engine(self):
        module = _load_whisper_server({"WHISPER_LOCAL_ENGINE": "openai-whisper"})
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
        mock_model.transcribe.assert_called_once()

    def test_transcribe_ignores_blank_api_key(self):
        module = _load_whisper_server({"OPENAI_API_KEY": "   "})
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.get_json()["provider"] == "faster-whisper"

    def test_health_stays_local_when_openai_base_url_set(self):
        module = _load_whisper_server({
            "OPENAI_API_KEY": "ollama",
            "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1",
        })
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["provider"] == "faster-whisper"

    def test_health_force_openai_api_with_base_url(self):
        module = _load_whisper_server({
            "OPENAI_API_KEY": "ollama",
            "OPENAI_BASE_URL": "http://127.0.0.1:11434/v1",
            "WHISPER_USE_OPENAI_API": "1",
        })
        client = module.app.test_client()
        response = client.get("/health")
        assert response.get_json()["provider"] == "openai-api"

    def test_health_force_local_despite_api_key(self):
        module = _load_whisper_server({
            "OPENAI_API_KEY": "sk-test",
            "WHISPER_USE_OPENAI_API": "0",
        })
        with patch.object(module, "FasterWhisperModel", MagicMock()):
            client = module.app.test_client()
            response = client.get("/health")
        assert response.get_json()["provider"] == "faster-whisper"
