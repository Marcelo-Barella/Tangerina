import importlib.util
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("model_loader", MagicMock())

_server_path = Path(__file__).resolve().parents[2] / "deploy" / "omnivoice" / "server.py"
_spec = importlib.util.spec_from_file_location("omnivoice_server", _server_path)
omnivoice_server = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(omnivoice_server)


@pytest.mark.unit
class TestOmnivoiceServerTimeout:
    def test_tts_timeout_uses_bounded_join(self):
        hung_thread = MagicMock(spec=threading.Thread)
        hung_thread.is_alive.return_value = True

        app = omnivoice_server.app
        client = app.test_client()

        with (
            patch.object(omnivoice_server, "_model_lock", MagicMock()),
            patch.object(
                omnivoice_server,
                "_generate_audio_timed",
                side_effect=omnivoice_server.InferenceTimeout(hung_thread),
            ),
            patch.object(omnivoice_server, "_inference_timeout_seconds", return_value=5),
        ):
            response = client.post("/tts", json={"text": "hello"})

        assert response.status_code == 504
        hung_thread.join.assert_called_once_with(timeout=5)
