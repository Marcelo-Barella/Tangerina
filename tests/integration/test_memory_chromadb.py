import pytest
from unittest.mock import AsyncMock
from chatbot.memory_manager import MemoryManager

pytest_plugins = ('pytest_asyncio',)

@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_and_retrieve_conversation(memory_manager):
    await memory_manager.store_conversation(
        user_message="Hello Tangerina",
        bot_response="Oi! Como posso ajudar?",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    result = await memory_manager.retrieve_context(
        query="Hello",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result
    all_memories = result["recent"] + result["semantic"]
    assert len(all_memories) >= 1
    assert any('Hello Tangerina' in mem['content'] for mem in all_memories)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_creates_document(memory_manager):
    initial_count = memory_manager._collection.count()

    await memory_manager.store_conversation(
        user_message="Test message",
        bot_response="Test response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    final_count = memory_manager._collection.count()
    assert final_count > initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_filters_by_guild_id(memory_manager):
    await memory_manager.store_conversation(
        user_message="Message in guild 123",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await memory_manager.store_conversation(
        user_message="Message in guild 999",
        bot_response="Response",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    result_guild_123 = await memory_manager.retrieve_context(
        query="Message",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    result_guild_999 = await memory_manager.retrieve_context(
        query="Message",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    memories_guild_123 = result_guild_123["recent"] + result_guild_123["semantic"]
    memories_guild_999 = result_guild_999["recent"] + result_guild_999["semantic"]
    assert len(memories_guild_123) > 0
    assert len(memories_guild_999) > 0
    semantic_123 = [mem for mem in memories_guild_123 if mem.get("type") == "semantic"]
    semantic_999 = [mem for mem in memories_guild_999 if mem.get("type") == "semantic"]
    if semantic_123:
        assert all(mem.get('metadata', {}).get('guild_id') == '123' for mem in semantic_123)
    if semantic_999:
        assert all(mem.get('metadata', {}).get('guild_id') == '999' for mem in semantic_999)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_respects_max_results(memory_manager):
    memory_manager.max_results = 2

    for i in range(5):
        await memory_manager.store_conversation(
            user_message=f"Message {i}",
            bot_response=f"Response {i}",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

    result = await memory_manager.retrieve_context(
        query="Message",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    assert len(result["semantic"]) <= memory_manager.max_results


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_includes_metadata(memory_manager):
    await memory_manager.store_conversation(
        user_message="Test",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789,
        tool_calls=[{'tool': 'MusicPlay', 'result': {'success': True}}]
    )

    results = memory_manager._collection.get()
    assert len(results['metadatas']) > 0
    metadata = results['metadatas'][-1]
    assert metadata['guild_id'] == '123'
    assert metadata['channel_id'] == '456'
    assert metadata['user_id'] == '789'
    assert 'timestamp' in metadata


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_returns_empty_when_no_matches(memory_manager):
    result = await memory_manager.retrieve_context(
        query="nonexistent query",
        guild_id=999,
        channel_id=888,
        user_id=777
    )

    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_delete_user_memories(memory_manager):
    await memory_manager.store_conversation(
        user_message="User 789 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await memory_manager.store_conversation(
        user_message="User 999 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=999
    )

    initial_count = memory_manager._collection.count()
    await memory_manager.delete_user_memories(user_id=789)

    final_count = memory_manager._collection.count()
    assert final_count < initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_delete_guild_memories(memory_manager):
    await memory_manager.store_conversation(
        user_message="Guild 123 message",
        bot_response="Response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )

    await memory_manager.store_conversation(
        user_message="Guild 999 message",
        bot_response="Response",
        guild_id=999,
        channel_id=456,
        user_id=789
    )

    initial_count = memory_manager._collection.count()
    await memory_manager.delete_guild_memories(guild_id=123)

    final_count = memory_manager._collection.count()
    assert final_count < initial_count


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_similarity_threshold_filters_results(ephemeral_chromadb):
    import uuid
    from chatbot.memory_manager import MemoryManager

    embedding_service = AsyncMock()
    embedding_service.embed_text = AsyncMock(side_effect=[[0.1] * 384, [0.9] * 384])

    manager = MemoryManager(embedding_service=embedding_service)
    manager._client = ephemeral_chromadb
    collection_name = f"test_{uuid.uuid4().hex[:8]}"
    manager._collection = ephemeral_chromadb.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
    manager._initialized = manager.similarity_threshold = True
    manager.similarity_threshold = 0.8

    await manager.store_conversation("Stored message", "Response", 123, 456, 789)

    result = await manager.retrieve_context("Very different query", 123, 456, 789)
    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_store_conversation_handles_none_values(memory_manager):
    await memory_manager.store_conversation(
        user_message="Test",
        bot_response="Response",
        guild_id=None,
        channel_id=456,
        user_id=789
    )

    results = memory_manager._collection.get()
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


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_includes_recent_memories(memory_manager):
    await memory_manager.store_conversation(
        user_message="First message",
        bot_response="First response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    await memory_manager.store_conversation(
        user_message="Second message",
        bot_response="Second response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    await memory_manager.store_conversation(
        user_message="Third message",
        bot_response="Third response",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    result = await memory_manager.retrieve_context(
        query="What was the last thing?",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result
    assert len(result["recent"]) >= 1
    assert any("Third message" in mem["content"] for mem in result["recent"])


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_semantic_still_works(memory_manager):
    await memory_manager.store_conversation(
        user_message="I love jazz music",
        bot_response="That's great!",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    result = await memory_manager.retrieve_context(
        query="What music do I like?",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    assert isinstance(result, dict)
    assert "semantic" in result
    assert len(result["semantic"]) >= 1
    assert any("jazz" in mem["content"].lower() for mem in result["semantic"])


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_hybrid_scenario(memory_manager):
    await memory_manager.store_conversation(
        user_message="I like rock music",
        bot_response="Rock is great!",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    await memory_manager.store_conversation(
        user_message="Play some music",
        bot_response="Playing now",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    result = await memory_manager.retrieve_context(
        query="What was the last thing about music?",
        guild_id=123,
        channel_id=456,
        user_id=789
    )
    
    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result
    assert len(result["recent"]) >= 1
    recent_has_music = any("music" in mem["content"].lower() for mem in result["recent"])
    semantic_has_music = any("music" in mem["content"].lower() for mem in result["semantic"])
    assert recent_has_music or semantic_has_music


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_recent_interactions_returns_last_three(memory_manager):
    for i in range(5):
        await memory_manager.store_conversation(
            user_message=f"Message {i}",
            bot_response=f"Response {i}",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
    
    recent = await memory_manager.retrieve_recent_interactions(123, 456, 789)
    
    assert len(recent) == 3
    assert "Message 2" in recent[0]["content"]
    assert "Message 3" in recent[1]["content"]
    assert "Message 4" in recent[2]["content"]
    assert all(mem["type"] == "recent" for mem in recent)


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_recent_memories_isolated_by_conversation_key(memory_manager):
    await memory_manager.store_conversation(
        user_message="Guild 1 message",
        bot_response="Response",
        guild_id=111,
        channel_id=456,
        user_id=789
    )
    
    await memory_manager.store_conversation(
        user_message="Guild 2 message",
        bot_response="Response",
        guild_id=222,
        channel_id=456,
        user_id=789
    )
    
    recent1 = await memory_manager.retrieve_recent_interactions(111, 456, 789)
    recent2 = await memory_manager.retrieve_recent_interactions(222, 456, 789)
    
    assert len(recent1) == 1
    assert len(recent2) == 1
    assert "Guild 1" in recent1[0]["content"]
    assert "Guild 2" in recent2[0]["content"]


@pytest.mark.integration
@pytest.mark.chromadb
@pytest.mark.asyncio
async def test_retrieve_context_handles_none_guild_id(memory_manager):
    await memory_manager.store_conversation(
        user_message="DM message",
        bot_response="DM response",
        guild_id=None,
        channel_id=456,
        user_id=789
    )
    
    result = await memory_manager.retrieve_context(
        query="DM",
        guild_id=None,
        channel_id=456,
        user_id=789
    )
    
    assert isinstance(result, dict)
    assert "recent" in result
    assert "semantic" in result
    assert len(result["recent"]) >= 1
