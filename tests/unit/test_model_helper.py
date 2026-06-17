import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from chatbot.model_helper import (
    build_tools_schema,
    build_tool_mapping,
    _normalize_integer_ids,
    normalize_context,
    load_tangerina_persona,
    build_system_text,
    DEFAULT_PERSONA_FALLBACK,
    SYSTEM_PROMPT_TEMPLATE,
)
from chatbot.voice_join import is_join_voice_request, text_claims_voice_join
from chatbot.tool_response import resolve_tool_response

@pytest.mark.unit
class TestBuildToolsSchema:
    def test_build_tools_schema_returns_list(self):
        schema = build_tools_schema()
        assert isinstance(schema, list)
        assert len(schema) > 0

    def test_build_tools_schema_has_tools(self):
        schema = build_tools_schema()
        assert len(schema) > 0

    def test_all_tools_have_function_key(self):
        schema = build_tools_schema()
        for tool in schema:
            assert 'type' in tool
            assert tool['type'] == 'function'
            assert 'function' in tool
            assert 'name' in tool['function']
            assert 'description' in tool['function']
            assert 'parameters' in tool['function']

    def test_first_tool_is_get_canais(self):
        schema = build_tools_schema()
        assert schema[0]['function']['name'] == 'GET_Canais'

    def test_all_tools_have_required_fields(self):
        schema = build_tools_schema()
        for tool in schema:
            params = tool['function']['parameters']
            assert 'type' in params
            assert params['type'] == 'object'
            assert 'properties' in params
            assert 'required' in params


@pytest.mark.unit
class TestBuildToolMapping:
    def test_build_tool_mapping_returns_dict(self):
        schema = build_tools_schema()
        mapping = build_tool_mapping(schema)
        assert isinstance(mapping, dict)

    def test_build_tool_mapping_has_correct_keys(self):
        schema = build_tools_schema()
        mapping = build_tool_mapping(schema)
        assert 'MusicPlay' in mapping
        assert 'GET_Canais' in mapping
        assert 'SEND_Mensagem' in mapping

    def test_mapping_contains_required_and_properties(self):
        schema = build_tools_schema()
        mapping = build_tool_mapping(schema)
        for tool_name, tool_info in mapping.items():
            assert 'required' in tool_info
            assert 'properties' in tool_info
            assert isinstance(tool_info['required'], list)
            assert isinstance(tool_info['properties'], dict)

    def test_music_play_required_parameters(self):
        schema = build_tools_schema()
        mapping = build_tool_mapping(schema)
        assert 'guild_id' in mapping['MusicPlay']['required']
        assert 'channel_id' in mapping['MusicPlay']['required']
        assert 'query' in mapping['MusicPlay']['required']


@pytest.mark.unit
class TestNormalizeIntegerIds:
    def test_normalize_integer_ids_converts_float_to_int(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'},
                    'channel_id': {'type': 'integer'}
                }
            }
        }
        params = {'guild_id': 123.0, 'channel_id': 456.0, 'query': 'test'}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == 123
        assert result['channel_id'] == 456
        assert isinstance(result['guild_id'], int)
        assert isinstance(result['channel_id'], int)

    def test_normalize_integer_ids_converts_string_to_int(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'}
                }
            }
        }
        params = {'guild_id': '123'}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == 123
        assert isinstance(result['guild_id'], int)

    def test_normalize_integer_ids_preserves_non_integer_floats(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'}
                }
            }
        }
        params = {'guild_id': 123.45}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == 123.45

    def test_normalize_integer_ids_preserves_non_numeric_strings(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'query': {'type': 'string'}
                }
            }
        }
        params = {'query': 'test song'}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['query'] == 'test song'

    def test_normalize_integer_ids_unknown_tool_returns_unchanged(self):
        tool_mapping = {}
        params = {'guild_id': 123.0}
        result = _normalize_integer_ids('UnknownTool', params, tool_mapping)
        assert result == params

    def test_normalize_integer_ids_handles_string_float(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'}
                }
            }
        }
        params = {'guild_id': '123.0'}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == 123
        assert isinstance(result['guild_id'], int)
    
    def test_normalize_integer_ids_handles_unicode_in_string_parameters(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'query': {'type': 'string'},
                    'guild_id': {'type': 'integer'}
                }
            }
        }
        params = {
            'guild_id': 123,
            'query': 'Música com acentos: café, coração, ação'
        }
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['query'] == 'Música com acentos: café, coração, ação'
        assert result['guild_id'] == 123
    
    def test_normalize_integer_ids_handles_unicode_emojis_in_string_parameters(self):
        tool_mapping = {
            'SEND_Mensagem': {
                'properties': {
                    'text': {'type': 'string'},
                    'channel_id': {'type': 'integer'}
                }
            }
        }
        params = {
            'channel_id': 456,
            'text': 'Hello 🌟 World 🎵 Test 🎶'
        }
        result = _normalize_integer_ids('SEND_Mensagem', params, tool_mapping)
        assert result['text'] == 'Hello 🌟 World 🎵 Test 🎶'
        assert result['channel_id'] == 456
    
    def test_normalize_integer_ids_handles_extremely_large_guild_id(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'},
                    'channel_id': {'type': 'integer'}
                }
            }
        }
        max_int64 = 2**63 - 1
        params = {
            'guild_id': max_int64,
            'channel_id': 456,
            'query': 'test'
        }
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == max_int64
        assert isinstance(result['guild_id'], int)
    
    def test_normalize_integer_ids_handles_extremely_large_guild_id_as_string(self):
        tool_mapping = {
            'MusicPlay': {
                'properties': {
                    'guild_id': {'type': 'integer'}
                }
            }
        }
        max_int64 = 2**63 - 1
        params = {'guild_id': str(max_int64)}
        result = _normalize_integer_ids('MusicPlay', params, tool_mapping)
        assert result['guild_id'] == max_int64
        assert isinstance(result['guild_id'], int)


@pytest.mark.unit
class TestNormalizeContext:
    def test_normalize_context_returns_empty_list_for_none(self):
        result = normalize_context(None)
        assert result == []

    def test_normalize_context_returns_empty_list_for_empty_list(self):
        result = normalize_context([])
        assert result == []

    def test_normalize_context_trims_to_last_10_messages(self):
        context = [{'content': f'message {i}'} for i in range(20)]
        result = normalize_context(context)
        assert len(result) == 10
        assert result[0]['content'] == 'message 10'
        assert result[-1]['content'] == 'message 19'

    def test_normalize_context_filters_empty_content(self):
        context = [
            {'content': 'valid'},
            {'content': ''},
            {'content': '  '},
            {'content': 'valid2'}
        ]
        result = normalize_context(context)
        assert len(result) == 2
        assert result[0]['content'] == 'valid'
        assert result[1]['content'] == 'valid2'

    def test_normalize_context_adds_user_role(self):
        context = [{'content': 'test message'}]
        result = normalize_context(context)
        assert result[0]['role'] == 'user'

    def test_normalize_context_strips_whitespace(self):
        context = [{'content': '  test message  '}]
        result = normalize_context(context)
        assert result[0]['content'] == 'test message'

    def test_normalize_context_filters_non_dict_items(self):
        context = [
            {'content': 'valid'},
            'invalid',
            None,
            {'content': 'valid2'}
        ]
        result = normalize_context(context)
        assert len(result) == 2

    def test_normalize_context_filters_non_string_content(self):
        context = [
            {'content': 'valid'},
            {'content': 123},
            {'content': None},
            {'content': 'valid2'}
        ]
        result = normalize_context(context)
        assert len(result) == 2
    
    def test_normalize_context_handles_more_than_10_empty_messages(self):
        context = [{'content': ''} for _ in range(15)]
        result = normalize_context(context)
        assert len(result) == 0
        assert result == []
    
    def test_normalize_context_handles_more_than_10_whitespace_only_messages(self):
        context = [{'content': '   '} for _ in range(12)]
        result = normalize_context(context)
        assert len(result) == 0
        assert result == []
    
    def test_normalize_context_handles_mixed_empty_and_valid_messages_over_10(self):
        context = [{'content': ''} for _ in range(8)] + [{'content': f'valid {i}'} for i in range(5)]
        result = normalize_context(context)
        assert len(result) == 5
        assert all('valid' in msg['content'] for msg in result)


@pytest.mark.unit
class TestLoadTangerinaPersona:
    def test_load_tangerina_persona_returns_string(self):
        result = load_tangerina_persona()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_tangerina_persona_has_fallback(self, monkeypatch):
        import builtins
        real_open = builtins.open

        def open_wrap(path, *args, **kwargs):
            if "tangerina_persona.txt" in str(path):
                raise FileNotFoundError(path)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", open_wrap)
        result = load_tangerina_persona()
        assert result == DEFAULT_PERSONA_FALLBACK

    def test_load_tangerina_persona_masculine_identity(self):
        result = load_tangerina_persona()
        assert "o Tangerina" in result
        assert "masculino" in result
        assert "Bergamota" in result
        assert "515664341194768385" in result
        assert "a Tangerina" not in result

    def test_load_tangerina_persona_xml_structure(self):
        persona_path = Path(__file__).parent.parent / "chatbot" / "tangerina_persona.txt"
        if not persona_path.is_file():
            pytest.skip("tangerina_persona.txt not present")
        result = load_tangerina_persona()
        for tag in ("<context>", "<instructions>", "<examples>", "<formatting>"):
            assert tag in result

    def test_load_tangerina_persona_falls_back_when_path_is_directory(self, tmp_path, monkeypatch):
        persona_dir = tmp_path / "tangerina_persona.txt"
        persona_dir.mkdir()
        fake_module = tmp_path / "model_helper.py"
        fake_module.touch()
        monkeypatch.setattr("chatbot.model_helper.__file__", str(fake_module))
        result = load_tangerina_persona()
        assert result == DEFAULT_PERSONA_FALLBACK

    def test_default_persona_fallback_contains_tangerina(self):
        assert 'Tangerina' in DEFAULT_PERSONA_FALLBACK

    def test_default_persona_fallback_has_identity_section(self):
        assert 'IDENTIDADE' in DEFAULT_PERSONA_FALLBACK

    def test_default_persona_fallback_masculine(self):
        assert 'masculino' in DEFAULT_PERSONA_FALLBACK
        assert 'o Tangerina' in DEFAULT_PERSONA_FALLBACK


@pytest.mark.unit
class TestBuildSystemText:
    def test_build_system_text_inserts_persona(self):
        persona = "Test persona content"
        result = build_system_text(persona)
        assert persona in result

    def test_build_system_text_includes_rules(self):
        persona = "Test persona"
        result = build_system_text(persona)
        assert 'REGRAS DE RESPOSTA' in result
        assert 'REGRAS DE FERRAMENTAS' in result

    def test_build_system_text_strips_whitespace(self):
        persona = "  Test persona  "
        result = build_system_text(persona)
        assert not result.startswith(' ')
        assert not result.endswith(' ')

    def test_build_system_text_uses_template(self):
        persona = "Test"
        result = build_system_text(persona)
        assert 'português brasileiro' in result
        assert 'ferramentas disponíveis' in result


@pytest.fixture
def test_chatbot():
    from chatbot.model_helper import BaseChatbot
    schema = build_tools_schema()
    mapping = build_tool_mapping(schema)

    class TestChatbot(BaseChatbot):
        def __init__(self):
            self._tool_mapping = mapping

        def _initialize_client(self, api_key):
            pass

        async def _make_api_request(self, messages, max_tokens=1000, tools=None):
            pass

        def _extract_tool_calls(self, choice):
            pass

        def _extract_choice_content(self, choice):
            pass

        def _get_models_to_try(self):
            pass

    return TestChatbot()


@pytest.mark.unit
class TestBaseChatbotValidateParameters:
    def test_validate_parameters_rejects_unknown_tool(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters('UnknownTool', {})
        assert not valid
        assert 'Unknown tool' in error

    def test_validate_parameters_detects_missing_required(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters('MusicPlay', {'guild_id': 123})
        assert not valid
        assert 'Missing required parameters' in error
        assert 'channel_id' in error
        assert 'query' in error

    def test_validate_parameters_validates_volume_range(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters('MusicVolume', {'guild_id': 123, 'volume': 150})
        assert not valid
        assert 'between 0 and 100' in error

        valid, error = test_chatbot._validate_parameters('MusicVolume', {'guild_id': 123, 'volume': -10})
        assert not valid
        assert 'between 0 and 100' in error

    def test_validate_parameters_accepts_valid_volume(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters('MusicVolume', {'guild_id': 123, 'volume': 50})
        assert valid
        assert error is None

    def test_validate_parameters_accepts_valid_tool_call(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters(
            'MusicPlay',
            {'guild_id': 123, 'channel_id': 456, 'query': 'test song'}
        )
        assert valid
        assert error is None


@pytest.mark.unit
class TestBaseChatbotBuildToolMessage:
    def test_build_tool_message_formats_dict_result(self, test_chatbot):
        result = test_chatbot._build_tool_message(
            'MusicPlay',
            {'success': True, 'song': 'test'},
            'call_123'
        )
        assert result['role'] == 'tool'
        assert result['name'] == 'MusicPlay'
        assert result['tool_call_id'] == 'call_123'
        content = json.loads(result['content'])
        assert content['success'] is True

    def test_build_tool_message_converts_non_dict_to_string(self, test_chatbot):
        result = test_chatbot._build_tool_message('TestTool', 'simple text')
        assert result['content'] == 'simple text'

    def test_build_tool_message_omits_tool_call_id_when_none(self, test_chatbot):
        result = test_chatbot._build_tool_message('TestTool', {'success': True})
        assert 'tool_call_id' not in result
    
    def test_validate_parameters_handles_unicode_in_query(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters(
            'MusicPlay',
            {'guild_id': 123, 'channel_id': 456, 'query': 'Música: café e coração'}
        )
        assert valid
        assert error is None
    
    def test_validate_parameters_handles_unicode_emojis_in_text(self, test_chatbot):
        valid, error = test_chatbot._validate_parameters(
            'SEND_Mensagem',
            {'channel_id': 123, 'text': 'Hello 🌟 World 🎵'}
        )
        assert valid
        assert error is None
    
    def test_validate_parameters_handles_extremely_large_guild_id(self, test_chatbot):
        max_int64 = 2**63 - 1
        valid, error = test_chatbot._validate_parameters(
            'MusicPlay',
            {'guild_id': max_int64, 'channel_id': 456, 'query': 'test'}
        )
        assert valid
        assert error is None


@pytest.mark.unit
class TestDeriveActionReply:
    def test_enter_channel_overrides_llm_text(self, test_chatbot):
        tool_calls = [
            {
                "tool": "EnterChannel",
                "result": {"success": True, "channel_name": "Geral"},
            }
        ]
        final = resolve_tool_response(
            tool_calls,
            content="Oi @Tangerina, você não está em um canal de voz.",
        )
        assert final == "Pronto, entrei no Geral!"

    def test_music_play_keeps_llm_text(self, test_chatbot):
        tool_calls = [
            {
                "tool": "EnterChannel",
                "result": {"success": True, "channel_name": "Geral"},
            },
            {
                "tool": "MusicSpotifyPlay",
                "result": {"success": True, "tracks_queued": 3},
            },
        ]
        llm_text = "Adicionei 3 músicas na fila."
        assert resolve_tool_response(tool_calls, content=llm_text) == llm_text

    def test_music_play_fallback_uses_enter_channel_reply(self, test_chatbot):
        tool_calls = [
            {
                "tool": "EnterChannel",
                "result": {"success": True, "channel_name": "Geral"},
            },
            {
                "tool": "MusicPlay",
                "result": {"success": True, "message": "Now playing: song"},
            },
        ]
        assert resolve_tool_response(tool_calls) == "Pronto, entrei no Geral!"

    def test_failed_enter_channel_keeps_llm_text(self, test_chatbot):
        tool_calls = [
            {
                "tool": "EnterChannel",
                "result": {"success": False, "error": "Failed"},
            }
        ]
        llm_text = "Não consegui entrar no canal."
        assert resolve_tool_response(tool_calls, content=llm_text) == llm_text

    def test_empty_llm_text_uses_enter_channel_reply(self, test_chatbot):
        tool_calls = [
            {
                "tool": "EnterChannel",
                "result": {"success": True, "channel_name": "Geral"},
            }
        ]
        assert resolve_tool_response(tool_calls) == "Pronto, entrei no Geral!"

    def test_leave_channel_overrides_llm_text(self, test_chatbot):
        tool_calls = [
            {
                "tool": "LeaveChannel",
                "result": {"success": True},
            }
        ]
        assert resolve_tool_response(tool_calls, content="Ainda estou no canal.") == "Saí do canal de voz."


@pytest.mark.unit
class TestJoinVoiceHelpers:
    def test_is_join_voice_request_matches_entra_na_chamada(self):
        assert is_join_voice_request("@Tangerina Entra na chamada por favor")

    def test_is_join_voice_request_rejects_how_to(self):
        assert not is_join_voice_request("explica como entrar no canal de voz")

    def test_text_claims_voice_join_matches_entrei_na_chamada(self):
        assert text_claims_voice_join("@1389316439193944275, entrei na chamada!")

    @pytest.mark.asyncio
    async def test_auto_enter_after_user_voice_channel(self, test_chatbot):
        test_chatbot.music_bot = MagicMock()
        voice_client = MagicMock()
        voice_client.channel.name = "Geral"
        test_chatbot.music_bot.join_voice_channel = AsyncMock(return_value=voice_client)

        tool_calls = [
            {
                "tool": "GET_UserVoiceChannel",
                "result": {
                    "success": True,
                    "in_voice_channel": True,
                    "guild_id": 123,
                    "channel_id": 456,
                    "channel_name": "Geral",
                },
            }
        ]
        await test_chatbot._auto_enter_voice_if_needed(
            "@Tangerina Entra na chamada por favor",
            tool_calls,
            {},
            123,
            789,
        )
        assert any(tc["tool"] == "EnterChannel" and tc["result"]["success"] for tc in tool_calls)
        test_chatbot.music_bot.join_voice_channel.assert_awaited_once_with(123, 456)

    @pytest.mark.asyncio
    async def test_auto_enter_skips_non_join_message(self, test_chatbot):
        test_chatbot.music_bot = MagicMock()
        test_chatbot.music_bot.join_voice_channel = AsyncMock()
        tool_calls = [
            {
                "tool": "GET_UserVoiceChannel",
                "result": {
                    "success": True,
                    "in_voice_channel": True,
                    "guild_id": 123,
                    "channel_id": 456,
                },
            }
        ]
        await test_chatbot._auto_enter_voice_if_needed(
            "qual é a fila de música?",
            tool_calls,
            {},
            123,
            789,
        )
        assert not any(tc["tool"] == "EnterChannel" for tc in tool_calls)
        test_chatbot.music_bot.join_voice_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_enter_skips_when_enter_already_succeeded(self, test_chatbot):
        test_chatbot.music_bot = MagicMock()
        test_chatbot.music_bot.join_voice_channel = AsyncMock()
        tool_calls = [
            {
                "tool": "GET_UserVoiceChannel",
                "result": {
                    "success": True,
                    "in_voice_channel": True,
                    "guild_id": 123,
                    "channel_id": 456,
                },
            },
            {
                "tool": "EnterChannel",
                "result": {"success": True, "channel_name": "Geral"},
            },
        ]
        await test_chatbot._auto_enter_voice_if_needed(
            "@Tangerina Entra na chamada por favor",
            tool_calls,
            {},
            123,
            789,
        )
        test_chatbot.music_bot.join_voice_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_mensagem_blocks_voice_join_claim(self, test_chatbot):
        test_chatbot.bot = MagicMock()
        result = await test_chatbot._handle_send_mensagem(
            {"channel_id": 1, "text": "entrei na chamada!"},
            {},
        )
        assert result["success"] is False
        test_chatbot.bot.get_channel.assert_not_called()


def _make_tool_calls_api_response(tool_name: str, params: dict, tool_call_id: str = "tc1"):
    tool_call = MagicMock()
    tool_call.id = tool_call_id
    tool_call.function.name = tool_name
    tool_call.function.arguments = json.dumps(params)
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message.content = None
    choice.message.tool_calls = [tool_call]
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.unit
class TestGenerateResponseApiFailure:
    @pytest.fixture
    def api_failure_chatbot(self):
        from chatbot.model_helper import BaseChatbot

        class ApiFailureChatbot(BaseChatbot):
            def __init__(self):
                self._tools_schema = build_tools_schema()
                self._tool_mapping = build_tool_mapping(self._tools_schema)
                self.persona_context = ""
                self._api_call = 0
                self.music_bot = MagicMock()
                voice_client = MagicMock()
                voice_client.channel.name = "Geral"
                self.music_bot.join_voice_channel = AsyncMock(return_value=voice_client)

            def _initialize_client(self, api_key):
                pass

            async def _make_api_request(self, messages, max_tokens=1000, tools=None):
                self._api_call += 1
                if self._api_call == 1:
                    return _make_tool_calls_api_response(
                        "EnterChannel", {"guild_id": 123, "channel_id": 456}
                    )
                raise RuntimeError("API 400")

            def _extract_tool_calls(self, choice):
                return getattr(choice.message, "tool_calls", None) or []

            def _extract_choice_content(self, choice):
                return getattr(choice.message, "content", None)

            def _get_models_to_try(self):
                return ["test-model"]

        return ApiFailureChatbot()

    @pytest.mark.asyncio
    async def test_api_failure_after_enter_returns_action_reply(self, api_failure_chatbot):
        text, tool_calls = await api_failure_chatbot.generate_response_with_tools(
            "Tangerina entra na chamada",
            guild_id=123,
            user_id=789,
        )
        assert text == "Pronto, entrei no Geral!"
        assert api_failure_chatbot._api_call == 2
        assert any(tc["tool"] == "EnterChannel" and tc["result"]["success"] for tc in tool_calls)
