import pytest
import json
from pathlib import Path
from chatbot.model_helper import (
    build_tools_schema,
    build_tool_mapping,
    _normalize_integer_ids,
    normalize_context,
    load_tangerina_persona,
    build_system_text,
    DEFAULT_PERSONA_FALLBACK,
    SYSTEM_PROMPT_TEMPLATE
)

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

    def test_load_tangerina_persona_has_fallback(self):
        result = load_tangerina_persona()
        assert len(result) > 0

    def test_default_persona_fallback_contains_tangerina(self):
        assert 'Tangerina' in DEFAULT_PERSONA_FALLBACK

    def test_default_persona_fallback_has_identity_section(self):
        assert 'IDENTIDADE' in DEFAULT_PERSONA_FALLBACK


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
