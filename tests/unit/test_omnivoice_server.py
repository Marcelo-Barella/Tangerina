import importlib.util
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" / "omnivoice" / "server.py"
SERVER_MODULE = "omnivoice_server_under_test"


def _install_server_stubs() -> None:
    deploy_dir = str(SERVER_PATH.parents[1])
    if deploy_dir not in sys.path:
        sys.path.insert(0, deploy_dir)
    if isinstance(sys.modules.get("flask"), MagicMock):
        del sys.modules["flask"]
    for name in ("soundfile", "torch", "model_loader"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()


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

    def test_health_stays_loading_until_warmup_finishes(self):
        server = _load_server_module()
        server._model_state = None
        server._model_ready = False
        server._load_error = None
        warmup_started = threading.Event()
        release_warmup = threading.Event()

        def fake_generate(**_kwargs):
            warmup_started.set()
            release_warmup.wait(timeout=2)

        mock_model = MagicMock()
        mock_model.generate.side_effect = fake_generate
        fake_state = {
            "model": mock_model,
            "device": "cpu",
            "precision": "int8",
            "model_id": "test",
            "vram_estimate_gb": 3.5,
        }

        with patch.object(server, "load_omnivoice_model", return_value=fake_state):
            loader = threading.Thread(target=server._warmup_model, daemon=True)
            loader.start()
            assert warmup_started.wait(timeout=2)

            with server.app.test_client() as client:
                loading = client.get("/health")
                assert loading.status_code == 503
                assert loading.get_json()["status"] == "loading"

            release_warmup.set()
            loader.join(timeout=2)

            with server.app.test_client() as client:
                ready = client.get("/health")
                assert ready.status_code == 200
                assert ready.get_json()["status"] == "ok"

    def test_health_returns_503_when_model_failed_to_load(self, server):
        server._load_error = "CUDA unavailable"
        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 503
        assert response.get_json()["status"] == "error"
        assert "CUDA unavailable" in response.get_json()["error"]

    def test_blocked_check_preserves_newer_hung_thread_during_stale_cleanup(self, server):
        dead_thread = threading.Thread(target=lambda: None)
        dead_thread.start()
        dead_thread.join()

        live_release = threading.Event()
        live_started = threading.Event()

        def live_hang() -> None:
            live_started.set()
            live_release.wait(timeout=5)

        live_thread = threading.Thread(target=live_hang)
        original_is_alive = threading.Thread.is_alive

        def is_alive_with_race(self):
            if self is dead_thread:
                live_thread.start()
                assert live_started.wait(timeout=1)
                server._hung_inference_thread = live_thread
            return original_is_alive(self)

        server._hung_inference_thread = dead_thread
        with patch.object(threading.Thread, "is_alive", is_alive_with_race):
            assert server._blocked_by_hung_inference() is False

        assert server._hung_inference_thread is live_thread
        assert server._blocked_by_hung_inference() is True

        live_release.set()
        live_thread.join(timeout=2)

    def test_health_returns_503_while_recovering_from_hung_inference(self, server):
        hang_started = threading.Event()
        hang_release = threading.Event()

        def hang_forever() -> None:
            hang_started.set()
            hang_release.wait(timeout=5)

        hung_thread = threading.Thread(target=hang_forever)
        hung_thread.start()
        assert hang_started.wait(timeout=1)

        server._model_state = {
            "device": "cuda:0",
            "precision": "int8",
            "model_id": "test-model",
            "vram_estimate_gb": 6,
        }
        server._model_ready = True
        server._hung_inference_thread = hung_thread

        client = server.app.test_client()
        response = client.get("/health")
        assert response.status_code == 503
        assert response.get_json()["status"] == "recovering"

        hang_release.set()
        hung_thread.join(timeout=2)

        response2 = client.get("/health")
        assert response2.status_code == 200
        assert response2.get_json()["status"] == "ok"

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

        def fake_named_tempfile(**kwargs):
            handle = MagicMock()
            path = str(tmp_path / f"temp-{len(created_paths)}.wav")
            created_paths.append(path)
            handle.name = path
            handle.__enter__ = MagicMock(return_value=handle)
            handle.__exit__ = MagicMock(return_value=False)
            return handle

        def fail_write(*_args, **_kwargs):
            raise OSError("disk full")

        with patch.object(server.tempfile, "NamedTemporaryFile", side_effect=fake_named_tempfile):
            sys.modules["soundfile"].write = fail_write
            client = server.app.test_client()
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 500
        assert created_paths
        assert not os.path.exists(created_paths[0])
