import pytest
from unittest.mock import AsyncMock
from chatbot.memory_manager import MemoryManager

pytest_plugins = ('pytest_asyncio',)

@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_and_retrieve_conversation(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(
        name="test_memory",
        metadata={"hnsw:space": "cosine"}
    )
    manager._initialized = True

    await manager.store_conversation(
        user_message="Hello Tangerina",
        bot_response="Oi! Como posso ajudar?",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    memories = await manager.retrieve_context(
        query="Hello",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    assert len(memories) >= 1
    assert any('Hello Tangerina' in mem['content'] for mem in memories)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_creates_document(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    initial_count = manager._collection.count()

    await manager.store_conversation(
        user_message="Test message",
        bot_response="Test response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    final_count = manager._collection.count()
    assert final_count > initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_filters_by_guild_id(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    await manager.store_conversation(
        user_message="Message in guild 123",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await manager.store_conversation(
        user_message="Message in guild 999",
        bot_response="Response",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    memories_guild_123 = await manager.retrieve_context(
        query="Message",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    memories_guild_999 = await manager.retrieve_context(
        query="Message",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    assert len(memories_guild_123) > 0
    assert len(memories_guild_999) > 0
    assert all(mem.get('guild_id') == '123' for mem in memories_guild_123)
    assert all(mem.get('guild_id') == '999' for mem in memories_guild_999)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_respects_max_results(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True
    manager.max_results = 2

    for i in range(5):
        await manager.store_conversation(
            user_message=f"Message {i}",
            bot_response=f"Response {i}",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

    memories = await manager.retrieve_context(
        query="Message",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    assert len(memories) <= manager.max_results


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_includes_metadata(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    await manager.store_conversation(
        user_message="Test",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789,
        tool_calls=[{'tool': 'MusicPlay', 'result': {'success': True}}]
    )

    results = manager._collection.get()
    assert len(results['metadatas']) > 0
    metadata = results['metadatas'][-1]
    assert metadata['guild_id'] == '123'
    assert metadata['channel_id'] == '456'
    assert metadata['user_id'] == '789'
    assert 'timestamp' in metadata


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_returns_empty_when_no_matches(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    memories = await manager.retrieve_context(
        query="nonexistent query",
        guild_id=999,
        channel_id=888,
        user_id=777
    )

    assert isinstance(memories, list)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_delete_user_memories(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    await manager.store_conversation(
        user_message="User 789 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await manager.store_conversation(
        user_message="User 999 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=999
    )

    initial_count = manager._collection.count()
    await manager.delete_user_memories(user_id=789, guild_id=123)

    final_count = manager._collection.count()
    assert final_count < initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_delete_guild_memories(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    await manager.store_conversation(
        user_message="Guild 123 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await manager.store_conversation(
        user_message="Guild 999 message",
        bot_response="Response",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    initial_count = manager._collection.count()
    await manager.delete_guild_memories(guild_id=123)

    final_count = manager._collection.count()
    assert final_count < initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_similarity_threshold_filters_results(ephemeral_chromadb):
    client, _ = ephemeral_chromadb

    embedding_service = AsyncMock()
    embedding_service.embed_text = AsyncMock(side_effect=[
        [0.1] * 384,
        [0.9] * 384
    ])

    manager = MemoryManager(embedding_service=embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True
    manager.similarity_threshold = 0.8

    await manager.store_conversation(
        user_message="Stored message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    memories = await manager.retrieve_context(
        query="Very different query",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    assert isinstance(memories, list)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_handles_none_values(ephemeral_chromadb, mock_embedding_service):
    client, _ = ephemeral_chromadb
    manager = MemoryManager(embedding_service=mock_embedding_service)
    manager._client = client
    manager._collection = client.create_collection(name="test_memory")
    manager._initialized = True

    await manager.store_conversation(
        user_message="Test",
        bot_response="Response",
        guild_id=None,
        channel_id=456,
        user_id=789
    )

    results = manager._collection.get()
    assert len(results['metadatas']) > 0


@pytest.mark.integration
@pytest.mark.chromadb
def test_memory_manager_initialization_with_ephemeral_client(mock_embedding_service):
    manager = MemoryManager(embedding_service=mock_embedding_service)
    assert manager.embedding_service is not None
    assert manager.max_results > 0
    assert 0 <= manager.similarity_threshold <= 0.4


@pytest.mark.integration
@pytest.mark.chromadb
def test_memory_manager_caps_similarity_threshold(mock_embedding_service):
    import os
    os.environ['MEMORY_SIMILARITY_THRESHOLD'] = '0.9'
    manager = MemoryManager(embedding_service=mock_embedding_service)
    assert manager.similarity_threshold == 0.4
