import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" / "piper" / "server.py"
SERVER_MODULE = "piper_server_under_test"


def _install_server_stubs() -> None:
    deploy_dir = str(SERVER_PATH.parents[1])
    if deploy_dir not in sys.path:
        sys.path.insert(0, deploy_dir)
    if isinstance(sys.modules.get("flask"), MagicMock):
        del sys.modules["flask"]


def _load_server_module():
    _install_server_stubs()
    sys.modules.pop(SERVER_MODULE, None)
    spec = importlib.util.spec_from_file_location(SERVER_MODULE, SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[SERVER_MODULE] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestPiperServerHealth:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def test_health_returns_ok(self, server):
        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"


@pytest.mark.unit
class TestPiperServerTtsValidation:
    @pytest.fixture
    def server(self):
        module = _load_server_module()
        module.PIPER_MODEL_PATH = "/fake/model.onnx"
        return module

    def test_tts_rejects_missing_json_body(self, server):
        client = server.app.test_client()
        response = client.post("/tts", data="not json", content_type="application/json")
        assert response.status_code == 400

    def test_tts_rejects_missing_text_field(self, server):
        client = server.app.test_client()
        response = client.post("/tts", json={})
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

    def test_tts_returns_500_when_model_missing(self, server):
        with patch.object(server, "os") as mock_os:
            mock_os.path.exists.return_value = False
            mock_os.getenv = server.os.getenv
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})
        assert response.status_code == 500
        assert "Model file not found" in response.get_json()["error"]

    def test_tts_returns_wav_on_success(self, server):
        with patch.object(server, "os") as mock_os:
            mock_os.path.exists.return_value = True
            mock_os.getenv = server.os.getenv

            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stderr = ""

            with patch.object(server, "subprocess") as mock_subprocess:
                mock_subprocess.run.return_value = mock_process
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 200
        assert response.mimetype == "audio/wav"
