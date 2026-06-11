import asyncio
import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _install_flask_route_stubs() -> None:
    discord = MagicMock()
    discord.Intents = MagicMock()
    sys.modules["discord"] = discord

    music_bot_module = ModuleType("features.music.music_bot")
    music_bot_module.MusicBot = MagicMock()
    music_bot_module.YTDLSource = MagicMock()
    sys.modules["features.music.music_bot"] = music_bot_module

    music_service_module = ModuleType("features.music.music_service")
    music_service_module.MusicService = MagicMock()
    sys.modules["features.music.music_service"] = music_service_module


def _create_test_app(speak_tts, omnivoice_enabled: bool = True):
    _install_flask_route_stubs()
    if "flask_routes" in sys.modules:
        del sys.modules["flask_routes"]
    from flask_routes import create_flask_app

    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    app, set_loop = create_flask_app(
        bot,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        speak_tts,
        omnivoice_enabled,
    )
    set_loop(asyncio.get_event_loop())
    app.config["TESTING"] = True
    return app


@pytest.mark.unit
class TestFlaskTtsRoutes:
    def test_piper_speak_rejects_missing_guild_id(self):
        app = _create_test_app(AsyncMock())
        response = app.test_client().post(
            "/tts/piper/speak",
            json={"channel_id": 456, "text": "test"},
        )
        assert response.status_code == 400

    def test_piper_speak_rejects_missing_text(self):
        app = _create_test_app(AsyncMock())
        response = app.test_client().post(
            "/tts/piper/speak",
            json={"guild_id": 123, "channel_id": 456},
        )
        assert response.status_code == 400

    def test_piper_speak_passes_provider_to_handler(self):
        speak_tts = AsyncMock(return_value={"success": True})
        app = _create_test_app(speak_tts)

        with patch("flask_routes.asyncio.run_coroutine_threadsafe") as mock_run:
            mock_future = MagicMock()
            mock_future.result.return_value = {"success": True}
            mock_run.return_value = mock_future

            response = app.test_client().post(
                "/tts/piper/speak",
                json={"guild_id": 123, "channel_id": 456, "text": "hello"},
            )

        assert response.status_code == 200
        speak_tts.assert_called_once_with(123, 456, "hello", "piper")

    def test_piper_speak_timeout_returns_504(self):
        app = _create_test_app(AsyncMock())

        with patch("flask_routes.asyncio.run_coroutine_threadsafe") as mock_run:
            mock_future = MagicMock()
            mock_future.result.side_effect = TimeoutError()
            mock_run.return_value = mock_future

            response = app.test_client().post(
                "/tts/piper/speak",
                json={"guild_id": 123, "channel_id": 456, "text": "hello"},
            )

        assert response.status_code == 504
        data = json.loads(response.data)
        assert "timed out" in data["error"].lower()

    def test_omnivoice_speak_returns_503_when_not_configured(self):
        app = _create_test_app(AsyncMock(), omnivoice_enabled=False)
        response = app.test_client().post(
            "/tts/omnivoice/speak",
            json={"guild_id": 123, "channel_id": 456, "text": "hello"},
        )
        assert response.status_code == 503
        assert "not configured" in response.get_json()["error"]

    def test_omnivoice_speak_passes_provider_to_handler(self):
        speak_tts = AsyncMock(return_value={"success": True})
        app = _create_test_app(speak_tts)

        with patch("flask_routes.asyncio.run_coroutine_threadsafe") as mock_run:
            mock_future = MagicMock()
            mock_future.result.return_value = {"success": True}
            mock_run.return_value = mock_future

            response = app.test_client().post(
                "/tts/omnivoice/speak",
                json={"guild_id": 123, "channel_id": 456, "text": "hello"},
            )

        assert response.status_code == 200
        speak_tts.assert_called_once_with(123, 456, "hello", "omnivoice")

    def test_omnivoice_speak_timeout_returns_504(self):
        app = _create_test_app(AsyncMock())

        with patch("flask_routes.asyncio.run_coroutine_threadsafe") as mock_run:
            mock_future = MagicMock()
            mock_future.result.side_effect = TimeoutError()
            mock_run.return_value = mock_future

            response = app.test_client().post(
                "/tts/omnivoice/speak",
                json={"guild_id": 123, "channel_id": 456, "text": "hello"},
            )

        assert response.status_code == 504
        data = json.loads(response.data)
        assert data["error"] == "OmniVoice TTS request timed out"
