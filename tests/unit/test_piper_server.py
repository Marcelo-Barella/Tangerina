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
class TestPiperServerTtsValidation:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def test_tts_rejects_missing_json_body(self, server):
        client = server.app.test_client()
        response = client.post("/tts", data="not json", content_type="application/json")
        assert response.status_code == 400

    def test_tts_rejects_emoji_only_text(self, server):
        client = server.app.test_client()
        response = client.post("/tts", json={"text": "😀🎉"})
        assert response.status_code == 400
        assert "unsupported characters" in response.get_json()["error"]

    def test_tts_returns_500_when_model_missing(self, server):
        with patch.object(server, "PIPER_MODEL_PATH", "/nonexistent/model.onnx"):
            with patch("os.path.exists", return_value=False):
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})
        assert response.status_code == 500
        assert "Model file not found" in response.get_json()["error"]

    def test_tts_returns_500_on_piper_failure(self, server):
        failed = MagicMock(returncode=1, stderr="piper crashed")
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=failed):
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})
        assert response.status_code == 500
        assert "piper crashed" in response.get_json()["error"]
