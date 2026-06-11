import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


def _install_app_stubs() -> None:
    discord = MagicMock()
    discord.Intents = MagicMock()
    discord.Intents.default = MagicMock(return_value=MagicMock())
    commands = ModuleType("discord.ext.commands")
    commands.Bot = MagicMock(return_value=MagicMock())
    sys.modules["discord"] = discord
    sys.modules["discord.ext"] = ModuleType("discord.ext")
    sys.modules["discord.ext.commands"] = commands
    sys.modules["yt_dlp"] = MagicMock()
    dotenv_module = ModuleType("dotenv")
    dotenv_module.load_dotenv = MagicMock()
    sys.modules["dotenv"] = dotenv_module
    aiohttp_module = ModuleType("aiohttp")
    aiohttp_module.ClientSession = MagicMock()
    aiohttp_module.ClientTimeout = MagicMock()
    sys.modules["aiohttp"] = aiohttp_module

    music_bot_module = ModuleType("features.music.music_bot")
    music_bot_module.MusicBot = MagicMock(return_value=MagicMock())
    music_bot_module.YTDLSource = MagicMock()
    sys.modules["features.music.music_bot"] = music_bot_module

    music_service_module = ModuleType("features.music.music_service")
    music_service_module.MusicService = MagicMock(return_value=MagicMock())
    music_service_module._resolve_voice_channel = MagicMock()
    sys.modules["features.music.music_service"] = music_service_module

    tts_handler_module = ModuleType("features.tts.tts_handler")
    tts_handler_module.speak_tts_unified = MagicMock()
    sys.modules["features.tts.tts_handler"] = tts_handler_module

    flask_routes_module = ModuleType("flask_routes")
    flask_routes_module.create_flask_app = MagicMock(return_value=(MagicMock(), MagicMock()))
    sys.modules["flask_routes"] = flask_routes_module


def _reload_app(env: dict[str, str]):
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    _install_app_stubs()
    with patch.dict("os.environ", env, clear=True):
        return importlib.import_module("app")


@pytest.mark.unit
class TestAppOmnivoiceRegistration:
    def test_registers_omnivoice_sidecar_when_default_provider_is_elevenlabs(self):
        mock_client = MagicMock()
        env = {
            "DISCORD_BOT_TOKEN": "test-token",
            "TTS_PROVIDER": "elevenlabs",
            "ELEVEN_API_KEY": "test-eleven-key",
            "OMNIVOICE_API_URL": "http://localhost:5003",
        }
        with patch(
            "features.tts.http_tts.create_omnivoice_client", return_value=mock_client
        ) as factory:
            app_module = _reload_app(env)
        assert "omnivoice" in app_module.tts_providers
        assert app_module.tts_providers["omnivoice"] is mock_client
        factory.assert_called_once()

    def test_does_not_register_omnivoice_without_api_url(self):
        mock_factory = MagicMock()
        env = {
            "DISCORD_BOT_TOKEN": "test-token",
            "TTS_PROVIDER": "elevenlabs",
            "ELEVEN_API_KEY": "test-eleven-key",
        }
        with patch("features.tts.http_tts.create_omnivoice_client", mock_factory):
            app_module = _reload_app(env)
        assert "omnivoice" not in app_module.tts_providers
        mock_factory.assert_not_called()

    def test_omnivoice_primary_provider_does_not_double_register(self):
        mock_client = MagicMock()
        env = {
            "DISCORD_BOT_TOKEN": "test-token",
            "TTS_PROVIDER": "omnivoice",
            "OMNIVOICE_API_URL": "http://localhost:5003",
        }
        with patch(
            "features.tts.http_tts.create_omnivoice_client", return_value=mock_client
        ) as factory:
            app_module = _reload_app(env)
        assert "omnivoice" in app_module.tts_providers
        factory.assert_called_once()
