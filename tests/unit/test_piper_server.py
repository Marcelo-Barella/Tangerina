import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.sidecar_server_test_utils import fake_named_tempfile, load_sidecar_server


@pytest.mark.unit
class TestPiperServerTts:
    @pytest.fixture
    def server(self, tmp_path):
        module = load_sidecar_server("piper/server.py", "piper_server_under_test")
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"onnx")
        module.PIPER_MODEL_PATH = str(model_path)
        return module

    def test_tts_returns_wav_on_success(self, server, tmp_path):
        created_paths: list[str] = []
        mock_process = MagicMock()
        mock_process.returncode = 0

        def create_output_on_run(*_args, **_kwargs):
            Path(created_paths[-1]).write_bytes(b"RIFFWAVE")
            return mock_process

        with patch.object(
            server.tempfile,
            "NamedTemporaryFile",
            side_effect=lambda **kwargs: fake_named_tempfile(created_paths, tmp_path, **kwargs),
        ):
            with patch.object(server.subprocess, "run", side_effect=create_output_on_run) as mock_run:
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 200
        assert response.mimetype == "audio/wav"
        mock_run.assert_called_once()

    def test_tts_subprocess_failure_unlinks_temp_file(self, server, tmp_path):
        created_paths: list[str] = []
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = "piper failed"

        with patch.object(
            server.tempfile,
            "NamedTemporaryFile",
            side_effect=lambda **kwargs: fake_named_tempfile(created_paths, tmp_path, **kwargs),
        ):
            with patch.object(server.subprocess, "run", return_value=mock_process):
                client = server.app.test_client()
                response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert created_paths
        assert not os.path.exists(created_paths[0])

    def test_tts_timeout_unlinks_temp_file(self, server, tmp_path):
        created_paths: list[str] = []

        with patch.object(
            server.tempfile,
            "NamedTemporaryFile",
            side_effect=lambda **kwargs: fake_named_tempfile(created_paths, tmp_path, **kwargs),
        ):
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
