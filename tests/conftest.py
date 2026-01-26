import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_GUILD_ID = 123456789
TEST_CHANNEL_ID = 987654321
TEST_USER_ID = 515664341194768385
EMBEDDING_DIM = 384

@pytest.fixture
def mock_guild():
    guild = MagicMock()
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.voice_channels = guild.text_channels = []
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
    bot.get_guild = bot.get_channel = MagicMock(return_value=None)
    bot.loop = asyncio.get_event_loop()
    yield bot
    bot.reset_mock()

@pytest.fixture
def mock_music_bot():
    music_bot = MagicMock()
    music_bot.voice_clients = music_bot.queues = music_bot.current_songs = music_bot.original_volumes = {}
    mock_voice_client = MagicMock()
    mock_voice_client.channel = MagicMock()
    mock_voice_client.channel.name = 'Test Channel'
    music_bot.join_voice_channel = AsyncMock(return_value=mock_voice_client)
    music_bot.play_next = AsyncMock()
    yield music_bot
    music_bot.reset_mock()

@pytest.fixture
def mock_music_service():
    service = MagicMock()
    for method in ['play_music', 'stop_music', 'skip_music', 'pause_music', 'resume_music', 'leave_music']:
        getattr(service, method).return_value = {'success': True}
    service.set_volume.return_value = {'success': True, 'volume': 50}
    service.get_queue.return_value = {'queue': [], 'current': None}
    service.get_user_voice_channel = AsyncMock()
    yield service
    service.reset_mock()

@pytest.fixture
def mock_music_service_success():
    service = MagicMock()
    service.play_music = AsyncMock(return_value={'success': True, 'message': 'Playing...'})
    service.stop_music = AsyncMock(return_value={'success': True, 'message': 'Stopped'})
    service.skip_music = AsyncMock(return_value={'success': True, 'message': 'Skipped'})
    service.pause_music = AsyncMock(return_value={'success': True, 'message': 'Paused'})
    service.resume_music = AsyncMock(return_value={'success': True, 'message': 'Resumed'})
    service.leave_music = AsyncMock(return_value={'success': True, 'message': 'Left'})
    service.set_volume = AsyncMock(return_value={'success': True, 'volume': 50})
    service.get_queue = AsyncMock(return_value={'queue': [], 'current': None})
    service.get_user_voice_channel = AsyncMock(return_value={'success': True, 'channel_id': 456})
    yield service
    service.reset_mock()

@pytest.fixture
def mock_music_service_unavailable():
    service = MagicMock()
    service.play_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.stop_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.skip_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.pause_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.resume_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.leave_music = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.set_volume = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    service.get_queue = AsyncMock(return_value={'queue': [], 'current': None})
    service.get_user_voice_channel = AsyncMock(return_value={'success': False, 'error': 'Service unavailable'})
    yield service
    service.reset_mock()

@pytest.fixture
def flask_client(mock_bot, mock_music_bot, mock_music_service):
    from flask_routes import create_flask_app

    chatbot = MagicMock()
    chatbot.generate_response = AsyncMock(return_value="Test response")
    speak_funcs = [AsyncMock() for _ in range(2)]

    app, set_loop = create_flask_app(mock_bot, mock_music_bot, mock_music_service, chatbot, *speak_funcs)
    set_loop(asyncio.get_event_loop())
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client

@pytest.fixture
def flask_client_mocked_music(mock_bot, mock_music_bot, mock_music_service_success):
    from flask_routes import create_flask_app

    chatbot = MagicMock()
    chatbot.generate_response = AsyncMock(return_value="Test response")
    speak_funcs = [AsyncMock(return_value={'success': True}) for _ in range(2)]

    app, set_loop = create_flask_app(mock_bot, mock_music_bot, mock_music_service_success, chatbot, *speak_funcs)
    set_loop(asyncio.get_event_loop())
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client

@pytest.fixture
def flask_client_integration_music(mock_bot, mock_music_bot, mock_music_service_unavailable):
    from flask_routes import create_flask_app

    chatbot = MagicMock()
    chatbot.generate_response = AsyncMock(return_value="Test response")
    speak_funcs = [AsyncMock(return_value={'success': False, 'error': 'Service unavailable'}) for _ in range(2)]

    app, set_loop = create_flask_app(mock_bot, mock_music_bot, mock_music_service_unavailable, chatbot, *speak_funcs)
    set_loop(asyncio.get_event_loop())
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client

@pytest.fixture
def ephemeral_chromadb():
    try:
        import chromadb
        import uuid
        client = chromadb.EphemeralClient()
        yield client
        for collection in client.list_collections():
            try:
                client.delete_collection(collection.name)
            except Exception:
                pass
    except ImportError:
        pytest.skip("ChromaDB not installed")

@pytest.fixture
def memory_manager(ephemeral_chromadb, mock_embedding_service):
    import uuid
    from chatbot.memory_manager import MemoryManager
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = ephemeral_chromadb
    collection_name = f"test_{uuid.uuid4().hex[:8]}"
    manager._collection = ephemeral_chromadb.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    manager._initialized = True
    return manager

@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.embed_text = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
    service.embed_batch = AsyncMock(return_value=[[0.1] * EMBEDDING_DIM, [0.2] * EMBEDDING_DIM])
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
