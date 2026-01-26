import pytest
from unittest.mock import AsyncMock, MagicMock
from collections import deque
from chatbot.memory_manager import MemoryManager

pytest_plugins = ('pytest_asyncio',)

@pytest.mark.unit
@pytest.mark.asyncio
class TestRecentMemoryBuffer:
    def test_recent_interactions_initialized(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        assert hasattr(manager, 'recent_interactions')
        assert isinstance(manager.recent_interactions, dict)
        assert manager.recent_interactions == {}
        assert hasattr(manager, 'recent_buffer_size')
        assert manager.recent_buffer_size == 3

    def test_recent_buffer_size_from_env(self, mock_embedding_service, monkeypatch):
        monkeypatch.setenv('RECENT_MEMORY_BUFFER_SIZE', '5')
        manager = MemoryManager(embedding_service=mock_embedding_service)
        assert manager.recent_buffer_size == 5

    def test_get_conversation_key_with_guild_id(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        key = manager._get_conversation_key(123, 456, 789)
        assert key == "123_456_789"

    def test_get_conversation_key_without_guild_id(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        key = manager._get_conversation_key(None, 456, 789)
        assert key == "none_456_789"

    @pytest.mark.asyncio
    async def test_store_conversation_adds_to_buffer(self, memory_manager):
        await memory_manager.store_conversation(
            user_message="Hello",
            bot_response="Hi there",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
        
        key = memory_manager._get_conversation_key(123, 456, 789)
        assert key in memory_manager.recent_interactions
        buffer = memory_manager.recent_interactions[key]
        assert len(buffer) == 1
        assert buffer[0]["user_message"] == "Hello"
        assert buffer[0]["bot_response"] == "Hi there"
        assert "timestamp" in buffer[0]

    @pytest.mark.asyncio
    async def test_buffer_maintains_maxlen(self, memory_manager):
        memory_manager.recent_buffer_size = 2
        
        for i in range(5):
            await memory_manager.store_conversation(
                user_message=f"Message {i}",
                bot_response=f"Response {i}",
                guild_id=123,
                channel_id=456,
                user_id=789
            )
        
        key = memory_manager._get_conversation_key(123, 456, 789)
        buffer = memory_manager.recent_interactions[key]
        assert len(buffer) == 2
        assert buffer[0]["user_message"] == "Message 3"
        assert buffer[1]["user_message"] == "Message 4"

    @pytest.mark.asyncio
    async def test_retrieve_recent_interactions_returns_last_n(self, memory_manager):
        memory_manager.recent_buffer_size = 5
        
        for i in range(5):
            await memory_manager.store_conversation(
                user_message=f"Message {i}",
                bot_response=f"Response {i}",
                guild_id=123,
                channel_id=456,
                user_id=789
            )
        
        recent = await memory_manager.retrieve_recent_interactions(123, 456, 789, max_results=3)
        assert len(recent) == 3
        assert recent[0]["content"] == "User: Message 2 Bot: Response 2"
        assert recent[1]["content"] == "User: Message 3 Bot: Response 3"
        assert recent[2]["content"] == "User: Message 4 Bot: Response 4"
        assert all(mem["type"] == "recent" for mem in recent)
        assert all("timestamp" in mem for mem in recent)

    @pytest.mark.asyncio
    async def test_retrieve_recent_interactions_empty_when_no_buffer(self, memory_manager):
        recent = await memory_manager.retrieve_recent_interactions(123, 456, 789)
        assert recent == []

    @pytest.mark.asyncio
    async def test_buffer_isolation_across_conversations(self, memory_manager):
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
        
        key1 = memory_manager._get_conversation_key(111, 456, 789)
        key2 = memory_manager._get_conversation_key(222, 456, 789)
        
        assert key1 in memory_manager.recent_interactions
        assert key2 in memory_manager.recent_interactions
        assert memory_manager.recent_interactions[key1][0]["user_message"] == "Guild 1 message"
        assert memory_manager.recent_interactions[key2][0]["user_message"] == "Guild 2 message"

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_dict_with_recent_and_semantic(self, memory_manager):
        await memory_manager.store_conversation(
            user_message="Test message",
            bot_response="Test response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
        
        result = await memory_manager.retrieve_context(
            query="Test",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
        
        assert isinstance(result, dict)
        assert "recent" in result
        assert "semantic" in result
        assert isinstance(result["recent"], list)
        assert isinstance(result["semantic"], list)
        assert len(result["recent"]) > 0
        assert result["recent"][0]["type"] == "recent"

    @pytest.mark.asyncio
    async def test_retrieve_context_semantic_memories_have_type(self, memory_manager):
        await memory_manager.store_conversation(
            user_message="Semantic test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
        
        result = await memory_manager.retrieve_context(
            query="Semantic",
            guild_id=123,
            channel_id=456,
            user_id=789
        )
        
        if result["semantic"]:
            assert all(mem.get("type") == "semantic" for mem in result["semantic"])

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_recent_when_embedding_fails(self, memory_manager):
        memory_manager.embedding_service.embed_text = AsyncMock(return_value=None)

        await memory_manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        result = await memory_manager.retrieve_context(
            query="Test",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        assert isinstance(result, dict)
        assert "recent" in result
        assert "semantic" in result
        assert len(result["recent"]) > 0
        assert result["semantic"] == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestMemoryManagerInitialization:
    def test_init_without_embedding_service_creates_one(self, monkeypatch):
        from unittest.mock import MagicMock
        mock_create = MagicMock(return_value=MagicMock())
        monkeypatch.setattr('chatbot.embedding_service.create_embedding_service', mock_create)

        manager = MemoryManager(embedding_service=None)
        mock_create.assert_called_once()

    def test_init_with_chromadb_import_error(self, mock_embedding_service, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, 'chromadb', None)

        manager = MemoryManager(embedding_service=mock_embedding_service)
        assert manager._initialized is False

    def test_similarity_threshold_capped_at_04(self, mock_embedding_service, monkeypatch):
        monkeypatch.setenv('MEMORY_SIMILARITY_THRESHOLD', '0.9')
        manager = MemoryManager(embedding_service=mock_embedding_service)
        assert manager.similarity_threshold == 0.4


@pytest.mark.unit
@pytest.mark.asyncio
class TestMemoryManagerEdgeCases:
    @pytest.mark.asyncio
    async def test_store_conversation_without_embedding_service(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        manager._initialized = False

        await manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

    @pytest.mark.asyncio
    async def test_store_conversation_with_tool_calls(self, memory_manager):
        tool_calls = [{"name": "play_music", "args": {}}]

        await memory_manager.store_conversation(
            user_message="Play music",
            bot_response="Playing",
            guild_id=123,
            channel_id=456,
            user_id=789,
            tool_calls=tool_calls
        )

        key = memory_manager._get_conversation_key(123, 456, 789)
        assert key in memory_manager.recent_interactions

    @pytest.mark.asyncio
    async def test_store_conversation_embedding_failure(self, memory_manager):
        memory_manager.embedding_service.embed_text = AsyncMock(return_value=None)

        await memory_manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        key = memory_manager._get_conversation_key(123, 456, 789)
        assert key in memory_manager.recent_interactions

    @pytest.mark.asyncio
    async def test_store_conversation_chromadb_error(self, memory_manager):
        memory_manager._collection.add = MagicMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception):
            await memory_manager.store_conversation(
                user_message="Test",
                bot_response="Response",
                guild_id=123,
                channel_id=456,
                user_id=789
            )

    @pytest.mark.asyncio
    async def test_retrieve_context_not_initialized(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        manager._initialized = False

        result = await manager.retrieve_context(
            query="Test",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        assert result == {"recent": [], "semantic": []}

    @pytest.mark.asyncio
    async def test_retrieve_context_with_exception(self, memory_manager):
        memory_manager._collection.query = MagicMock(side_effect=Exception("Query error"))

        await memory_manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        result = await memory_manager.retrieve_context(
            query="Test",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        assert "recent" in result
        assert "semantic" in result
        assert len(result["recent"]) > 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestMemoryDeletion:
    @pytest.mark.asyncio
    async def test_delete_user_memories(self, memory_manager):
        await memory_manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        await memory_manager.delete_user_memories(789)

    @pytest.mark.asyncio
    async def test_delete_user_memories_not_initialized(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        manager._initialized = False

        await manager.delete_user_memories(789)

    @pytest.mark.asyncio
    async def test_delete_user_memories_no_results(self, memory_manager):
        memory_manager._collection.get = MagicMock(return_value={'ids': []})
        await memory_manager.delete_user_memories(999)

    @pytest.mark.asyncio
    async def test_delete_user_memories_with_error(self, memory_manager):
        memory_manager._collection.get = MagicMock(side_effect=Exception("Delete error"))
        await memory_manager.delete_user_memories(789)

    @pytest.mark.asyncio
    async def test_delete_guild_memories(self, memory_manager):
        await memory_manager.store_conversation(
            user_message="Test",
            bot_response="Response",
            guild_id=123,
            channel_id=456,
            user_id=789
        )

        await memory_manager.delete_guild_memories(123)

    @pytest.mark.asyncio
    async def test_delete_guild_memories_not_initialized(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        manager._initialized = False

        await manager.delete_guild_memories(123)

    @pytest.mark.asyncio
    async def test_delete_guild_memories_with_error(self, memory_manager):
        memory_manager._collection.get = MagicMock(side_effect=Exception("Delete error"))
        await memory_manager.delete_guild_memories(123)


@pytest.mark.unit
@pytest.mark.asyncio
class TestMemoryCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_memories(self, memory_manager):
        from datetime import datetime, timedelta

        memory_manager._collection.get = MagicMock(return_value={
            'ids': ['id1', 'id2'],
            'metadatas': [
                {'timestamp': (datetime.utcnow() - timedelta(days=50)).isoformat()},
                {'timestamp': datetime.utcnow().isoformat()}
            ]
        })
        memory_manager._collection.delete = MagicMock()

        await memory_manager.cleanup_old_memories()
        memory_manager._collection.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_memories_not_initialized(self, mock_embedding_service):
        manager = MemoryManager(embedding_service=mock_embedding_service)
        manager._initialized = False

        await manager.cleanup_old_memories()

    @pytest.mark.asyncio
    async def test_cleanup_old_memories_no_results(self, memory_manager):
        memory_manager._collection.get = MagicMock(return_value=None)
        await memory_manager.cleanup_old_memories()

    @pytest.mark.asyncio
    async def test_cleanup_old_memories_invalid_timestamp(self, memory_manager):
        memory_manager._collection.get = MagicMock(return_value={
            'ids': ['id1'],
            'metadatas': [{'timestamp': 'invalid'}]
        })
        memory_manager._collection.delete = MagicMock()

        await memory_manager.cleanup_old_memories()
        memory_manager._collection.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_old_memories_with_error(self, memory_manager):
        memory_manager._collection.get = MagicMock(side_effect=Exception("Cleanup error"))
        await memory_manager.cleanup_old_memories()
