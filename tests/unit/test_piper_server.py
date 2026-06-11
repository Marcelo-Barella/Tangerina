import importlib.util
import os
import subprocess
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


class _FakeTempFile:
    def __init__(self, path: str):
        self.name = path

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass


@pytest.mark.unit
class TestPiperServerValidation:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def test_tts_rejects_missing_json_body(self, server):
        client = server.app.test_client()
        response = client.post("/tts", data="not json", content_type="application/json")
        assert response.status_code == 400

    def test_tts_rejects_empty_text(self, server):
        client = server.app.test_client()
        response = client.post("/tts", json={"text": "   "})
        assert response.status_code == 400

    def test_tts_rejects_emoji_only_text_after_sanitization(self, server):
        with patch.object(server.os.path, "exists", return_value=True):
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "😀🎉"})
        assert response.status_code == 400
        assert "unsupported characters" in response.get_json()["error"]


@pytest.mark.unit
class TestPiperServerTempFileCleanup:
    @pytest.fixture
    def server(self):
        return _load_server_module()

    def _patch_temp_output(self, server, output_path: str):
        return patch.object(
            server.tempfile,
            "NamedTemporaryFile",
            return_value=_FakeTempFile(output_path),
        )

    def test_tts_unlinks_temp_file_when_piper_fails(self, server, tmp_path):
        output_path = str(tmp_path / "failed.wav")
        Path(output_path).touch()

        with self._patch_temp_output(server, output_path):
            with patch.object(server.os.path, "exists", return_value=True):
                with patch.object(
                    server.subprocess,
                    "run",
                    return_value=MagicMock(returncode=1, stderr="piper error"),
                ):
                    client = server.app.test_client()
                    response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert not os.path.exists(output_path)

    def test_tts_unlinks_temp_file_on_timeout(self, server, tmp_path):
        output_path = str(tmp_path / "timeout.wav")
        Path(output_path).touch()

        with self._patch_temp_output(server, output_path):
            with patch.object(server.os.path, "exists", return_value=True):
                with patch.object(
                    server.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(cmd=["piper"], timeout=30),
                ):
                    client = server.app.test_client()
                    response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 504
        assert not os.path.exists(output_path)

    def test_tts_unlinks_temp_file_when_audio_not_generated(self, server, tmp_path):
        output_path = str(tmp_path / "missing.wav")

        def exists(path):
            return path != output_path

        with self._patch_temp_output(server, output_path):
            with patch.object(server.os.path, "exists", side_effect=exists):
                with patch.object(
                    server.subprocess,
                    "run",
                    return_value=MagicMock(returncode=0),
                ):
                    client = server.app.test_client()
                    response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert not os.path.exists(output_path)

    def test_tts_removes_temp_file_after_successful_response(self, server, tmp_path):
        output_path = str(tmp_path / "success.wav")
        Path(output_path).write_bytes(b"RIFFWAVE")

        with self._patch_temp_output(server, output_path):
            with patch.object(server.os.path, "exists", return_value=True):
                with patch.object(
                    server.subprocess,
                    "run",
                    return_value=MagicMock(returncode=0),
                ):
                    client = server.app.test_client()
                    response = client.post("/tts", json={"text": "hello"})
                    assert response.status_code == 200
                    response.get_data()

        assert not os.path.exists(output_path)
