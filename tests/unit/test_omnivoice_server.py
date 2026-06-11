import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.sidecar_server_test_utils import fake_named_tempfile, load_sidecar_server


def _install_omnivoice_stubs() -> None:
    for name in ("soundfile", "torch", "model_loader"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()


@pytest.mark.unit
class TestOmnivoiceServerHealth:
    @pytest.fixture
    def server(self):
        _install_omnivoice_stubs()
        module = load_sidecar_server("omnivoice/server.py", "omnivoice_server_under_test")
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
        _install_omnivoice_stubs()
        module = load_sidecar_server("omnivoice/server.py", "omnivoice_server_under_test")
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

    def test_tts_timeout_returns_504_without_blocking_on_hung_thread(self, server):
        hang_started = threading.Event()
        hang_release = threading.Event()

        def hang_forever() -> None:
            hang_started.set()
            hang_release.wait(timeout=5)

        hung_thread = threading.Thread(target=hang_forever)
        hung_thread.start()
        assert hang_started.wait(timeout=1)

        def raise_timeout(_text: str):
            raise server.InferenceTimeout(hung_thread)

        server._generate_audio_timed = raise_timeout
        client = server.app.test_client()

        response = client.post("/tts", json={"text": "hello"})
        assert response.status_code == 504
        assert response.get_json()["error"] == "TTS generation timed out"

        response2 = client.post("/tts", json={"text": "hello again"})
        assert response2.status_code == 503
        assert "recovering" in response2.get_json()["error"]

        hang_release.set()
        hung_thread.join(timeout=2)

        server._generate_audio_timed = MagicMock(return_value=[b"\x00" * 16])
        sys.modules["soundfile"].write = MagicMock()
        response3 = client.post("/tts", json={"text": "recovered"})
        assert response3.status_code == 200
        assert response3.mimetype == "audio/wav"

    def test_tts_sf_write_failure_unlinks_temp_file(self, server, tmp_path):
        server._generate_audio_timed = MagicMock(return_value=[b"\x00" * 16])
        created_paths: list[str] = []

        def fail_write(*_args, **_kwargs):
            raise OSError("disk full")

        with patch.object(
            server.tempfile,
            "NamedTemporaryFile",
            side_effect=lambda **kwargs: fake_named_tempfile(created_paths, tmp_path, **kwargs),
        ):
            sys.modules["soundfile"].write = fail_write
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert created_paths
        assert not os.path.exists(created_paths[0])
