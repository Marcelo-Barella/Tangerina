import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" / "piper" / "server.py"
SERVER_MODULE = "piper_server_under_test"
_REAL_EXISTS = os.path.exists


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


def _model_exists_side_effect(module, path: str) -> bool:
    if path == module.PIPER_MODEL_PATH:
        return True
    return _REAL_EXISTS(path)


@pytest.mark.unit
class TestPiperServerTts:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def test_tts_success_deletes_temp_wav_after_response(self, server, tmp_path):
        captured_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            output_path = cmd[cmd.index("--output_file") + 1]
            captured_paths.append(output_path)
            with open(output_path, "wb") as handle:
                handle.write(b"RIFFWAVE")
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch(f"{SERVER_MODULE}.os.path.exists", side_effect=lambda p: _model_exists_side_effect(server, p)), \
             patch(f"{SERVER_MODULE}.subprocess.run", side_effect=fake_run):
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})
            response.get_data()

        assert response.status_code == 200
        assert captured_paths
        assert not os.path.exists(captured_paths[0])

    def test_tts_piper_failure_unlinks_temp(self, server):
        captured_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            output_path = cmd[cmd.index("--output_file") + 1]
            captured_paths.append(output_path)
            open(output_path, "wb").close()
            result = MagicMock()
            result.returncode = 1
            result.stderr = "piper failed"
            return result

        with patch(f"{SERVER_MODULE}.os.path.exists", side_effect=lambda p: _model_exists_side_effect(server, p)), \
             patch(f"{SERVER_MODULE}.subprocess.run", side_effect=fake_run):
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert captured_paths
        assert not os.path.exists(captured_paths[0])

    def test_tts_timeout_unlinks_temp(self, server):
        captured_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            output_path = cmd[cmd.index("--output_file") + 1]
            captured_paths.append(output_path)
            open(output_path, "wb").close()
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

        with patch(f"{SERVER_MODULE}.os.path.exists", side_effect=lambda p: _model_exists_side_effect(server, p)), \
             patch(f"{SERVER_MODULE}.subprocess.run", side_effect=fake_run):
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 504
        assert captured_paths
        assert not os.path.exists(captured_paths[0])

    def test_tts_missing_output_unlinks_temp(self, server):
        captured_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            output_path = cmd[cmd.index("--output_file") + 1]
            captured_paths.append(output_path)
            if _REAL_EXISTS(output_path):
                os.remove(output_path)
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch(f"{SERVER_MODULE}.os.path.exists", side_effect=lambda p: _model_exists_side_effect(server, p)), \
             patch(f"{SERVER_MODULE}.subprocess.run", side_effect=fake_run):
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert captured_paths
        assert not os.path.exists(captured_paths[0])

    def test_tts_rejects_missing_text_field(self, server):
        with patch(f"{SERVER_MODULE}.os.path.exists", return_value=True):
            client = server.app.test_client()
            response = client.post("/tts", json={"speed": 1.0})

        assert response.status_code == 400
        assert "text" in response.get_json()["error"]
