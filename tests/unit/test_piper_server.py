import importlib.util
import os
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
class TestPiperServerTts:
    @pytest.fixture
    def server(self, tmp_path):
        module = _load_server_module()
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"onnx")
        module.PIPER_MODEL_PATH = str(model_path)
        return module

    def test_tts_returns_wav_on_success(self, server, tmp_path):
        created_paths: list[str] = []

        def fake_named_tempfile(**kwargs):
            handle = MagicMock()
            path = str(tmp_path / f"temp-{len(created_paths)}.wav")
            created_paths.append(path)
            handle.name = path
            handle.__enter__ = MagicMock(return_value=handle)
            handle.__exit__ = MagicMock(return_value=False)
            return handle

        mock_process = MagicMock()
        mock_process.returncode = 0

        def create_output_on_run(*_args, **_kwargs):
            Path(created_paths[-1]).write_bytes(b"RIFFWAVE")
            return mock_process

        with patch.object(server.tempfile, "NamedTemporaryFile", side_effect=fake_named_tempfile):
            with patch.object(server.subprocess, "run", side_effect=create_output_on_run) as mock_run:
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 200
        assert response.mimetype == "audio/wav"
        mock_run.assert_called_once()

    def test_tts_subprocess_failure_unlinks_temp_file(self, server, tmp_path):
        created_paths: list[str] = []

        def fake_named_tempfile(**kwargs):
            handle = MagicMock()
            path = str(tmp_path / f"temp-{len(created_paths)}.wav")
            created_paths.append(path)
            handle.name = path
            handle.__enter__ = MagicMock(return_value=handle)
            handle.__exit__ = MagicMock(return_value=False)
            return handle

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = "piper failed"

        with patch.object(server.tempfile, "NamedTemporaryFile", side_effect=fake_named_tempfile):
            with patch.object(server.subprocess, "run", return_value=mock_process):
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert created_paths
        assert not os.path.exists(created_paths[0])

    def test_tts_timeout_unlinks_temp_file(self, server, tmp_path):
        created_paths: list[str] = []

        def fake_named_tempfile(**kwargs):
            handle = MagicMock()
            path = str(tmp_path / f"temp-{len(created_paths)}.wav")
            created_paths.append(path)
            handle.name = path
            handle.__enter__ = MagicMock(return_value=handle)
            handle.__exit__ = MagicMock(return_value=False)
            return handle

        with patch.object(server.tempfile, "NamedTemporaryFile", side_effect=fake_named_tempfile):
            with patch.object(
                server.subprocess,
                "run",
                side_effect=server.subprocess.TimeoutExpired("piper", 30),
            ):
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 504
        assert created_paths
        assert not os.path.exists(created_paths[0])
