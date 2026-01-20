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
