import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def mock_guild():
    guild = MagicMock()
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.voice_channels = []
    guild.text_channels = []
    guild.me = MagicMock()
    guild.get_channel = MagicMock(return_value=None)
    return guild

@pytest.fixture
def mock_voice_channel():
    channel = MagicMock()
    channel.id = 987654321
    channel.name = "Test Voice"
    channel.type = MagicMock()
    channel.type.name = "voice"
    return channel

@pytest.fixture
def mock_text_channel():
    channel = MagicMock()
    channel.id = 111222333
    channel.name = "Test Text"
    channel.send = AsyncMock()
    channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    return channel

@pytest.fixture
def mock_member():
    member = MagicMock()
    member.id = 515664341194768385
    member.display_name = "TestUser"
    member.voice = None
    return member

@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.get_guild = MagicMock(return_value=None)
    bot.get_channel = MagicMock(return_value=None)
    bot.loop = asyncio.get_event_loop()
    return bot

@pytest.fixture
def mock_music_bot():
    music_bot = MagicMock()
    music_bot.voice_clients = {}
    music_bot.queues = {}
    music_bot.current_songs = {}
    music_bot.original_volumes = {}
    music_bot.join_voice_channel = AsyncMock()
    music_bot.play_next = AsyncMock()
    return music_bot

@pytest.fixture
def mock_music_service():
    service = MagicMock()
    service.play_music = AsyncMock(return_value={'success': True})
    service.stop_music = AsyncMock(return_value={'success': True})
    service.skip_music = AsyncMock(return_value={'success': True})
    service.pause_music = AsyncMock(return_value={'success': True})
    service.resume_music = AsyncMock(return_value={'success': True})
    service.set_volume = AsyncMock(return_value={'success': True, 'volume': 50})
    service.get_queue = AsyncMock(return_value={'queue': [], 'current': None})
    service.get_user_voice_channel = AsyncMock()
    service.leave_music = AsyncMock(return_value={'success': True})
    return service

@pytest.fixture
def flask_client(mock_bot, mock_music_bot, mock_music_service):
    from flask_routes import create_flask_app

    chatbot = MagicMock()
    chatbot.generate_response = AsyncMock(return_value="Test response")
    speak_tts_func = AsyncMock()
    speak_piper_tts_func = AsyncMock()

    app, set_loop = create_flask_app(
        mock_bot,
        mock_music_bot,
        mock_music_service,
        chatbot,
        speak_tts_func,
        speak_piper_tts_func
    )

    set_loop(asyncio.get_event_loop())
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client

@pytest.fixture
def ephemeral_chromadb():
    try:
        import chromadb
        client = chromadb.EphemeralClient()
        collection = client.create_collection(
            name="test_collection",
            metadata={"hnsw:space": "cosine"}
        )
        yield client, collection
    except ImportError:
        pytest.skip("ChromaDB not installed")

@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.embed_text = AsyncMock(return_value=[0.1] * 384)
    service.embed_batch = AsyncMock(return_value=[[0.1] * 384, [0.2] * 384])
    return service

@pytest.fixture
def sample_tool_schema():
    from chatbot.model_helper import build_tools_schema
    return build_tools_schema()

@pytest.fixture
def sample_spotify_track():
    return {
        'name': 'Bohemian Rhapsody',
        'artists': [{'name': 'Queen'}],
        'id': 'abc123',
        'duration_ms': 354000
    }

@pytest.fixture
def sample_discord_message():
    return {
        'content': 'Tangerina, toca música',
        'author_id': 515664341194768385,
        'guild_id': 123456789,
        'channel_id': 987654321
    }
