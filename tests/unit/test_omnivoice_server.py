import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" / "omnivoice" / "server.py"
SERVER_MODULE = "omnivoice_server_under_test"


def _install_server_stubs() -> None:
    for name in ("soundfile", "torch", "model_loader"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()


def _load_server_module():
    _install_server_stubs()
    if SERVER_MODULE in sys.modules:
        return sys.modules[SERVER_MODULE]
    spec = importlib.util.spec_from_file_location(SERVER_MODULE, SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[SERVER_MODULE] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestOmnivoiceServerSanitizeText:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def test_strips_emoji_and_control_characters(self, server):
        assert server.sanitize_text("hello 😀 world\x00test") == "hello worldtest"

    def test_collapses_whitespace(self, server):
        assert server.sanitize_text("  hello   world  ") == "hello world"

    def test_returns_empty_string_for_emoji_only_input(self, server):
        assert server.sanitize_text("😀🎉") == ""


@pytest.mark.unit
class TestOmnivoiceServerHealth:
    @pytest.fixture
    def server(self):
        module = _load_server_module()
        module._model_state = None
        module._model_ready = False
        module._load_error = None
        return module

    def test_health_returns_503_while_model_is_loading(self, server):
        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 503
        assert response.get_json()["status"] == "loading"

    def test_health_returns_503_when_model_failed_to_load(self, server):
        server._load_error = "CUDA unavailable"
        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 503
        assert response.get_json()["status"] == "error"
        assert "CUDA unavailable" in response.get_json()["error"]

    def test_health_returns_ok_when_model_is_ready(self, server):
        server._model_state = {
            "device": "cuda:0",
            "precision": "int8",
            "model_id": "test-model",
            "vram_estimate_gb": 6,
        }
        server._model_ready = True
        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["device"] == "cuda:0"
        assert data["model"] == "test-model"


@pytest.mark.unit
class TestOmnivoiceServerTtsValidation:
    @pytest.fixture
    def server(self):
        module = _load_server_module()
        module._model_state = {
            "model": MagicMock(),
            "device": "cpu",
            "precision": "int8",
            "model_id": "test",
            "vram_estimate_gb": 1,
        }
        module._model_ready = True
        module._load_error = None
        return module

    def test_tts_rejects_missing_json_body(self, server):
        client = server.app.test_client()
        response = client.post("/tts", data="not json", content_type="application/json")
        assert response.status_code == 400

    def test_tts_rejects_empty_text(self, server):
        client = server.app.test_client()
        response = client.post("/tts", json={"text": "   "})
        assert response.status_code == 400

    def test_tts_rejects_emoji_only_text_after_sanitization(self, server):
        client = server.app.test_client()
        response = client.post("/tts", json={"text": "😀🎉"})
        assert response.status_code == 400
        assert "unsupported characters" in response.get_json()["error"]

    def test_tts_returns_wav_on_success(self, server):
        server._generate_audio_timed = MagicMock(return_value=[b"\x00" * 16])
        sys.modules["soundfile"].write = MagicMock()
        client = server.app.test_client()
        response = client.post("/tts", json={"text": "hello"})
        assert response.status_code == 200
        assert response.mimetype == "audio/wav"
