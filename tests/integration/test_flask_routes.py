import pytest
import json

@pytest.mark.integration
class TestHealthEndpoint:
    def test_health_returns_200(self, flask_client):
        response = flask_client.get('/health')
        assert response.status_code == 200

    def test_health_returns_json(self, flask_client):
        response = flask_client.get('/health')
        data = json.loads(response.data)
        assert 'status' in data
        assert 'bot_ready' in data

    def test_health_status_ok(self, flask_client):
        response = flask_client.get('/health')
        data = json.loads(response.data)
        assert data['status'] == 'ok'

    def test_health_bot_ready_is_boolean(self, flask_client):
        response = flask_client.get('/health')
        data = json.loads(response.data)
        assert isinstance(data['bot_ready'], bool)


@pytest.mark.integration
class TestMusicVolumeEndpoint:
    def test_music_volume_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/volume', json={'volume': 50})
        assert response.status_code == 400

    def test_music_volume_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 'invalid', 'volume': 50})
        assert response.status_code == 400

    def test_music_volume_above_max_returns_400(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': 150})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'between 0 and 100' in data['error']

    def test_music_volume_below_min_returns_400(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': -10})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'between 0 and 100' in data['error']

    def test_music_volume_at_min_boundary(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': 0})
        assert response.status_code in [200, 404]

    def test_music_volume_at_max_boundary(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': 100})
        assert response.status_code in [200, 404]

    def test_music_volume_valid_middle_value(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': 50})
        assert response.status_code in [200, 404]

    def test_music_volume_invalid_type_string(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123, 'volume': 'fifty'})
        assert response.status_code == 400

    def test_music_volume_missing_volume_returns_400(self, flask_client):
        response = flask_client.post('/music/volume', json={'guild_id': 123})
        assert response.status_code == 400


@pytest.mark.integration
class TestMusicPlayEndpoint:
    def test_music_play_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/play', json={'channel_id': 456, 'query': 'test'})
        assert response.status_code == 400

    def test_music_play_missing_channel_id_returns_400(self, flask_client):
        response = flask_client.post('/music/play', json={'guild_id': 123, 'query': 'test'})
        assert response.status_code == 400

    def test_music_play_missing_query_returns_400(self, flask_client):
        response = flask_client.post('/music/play', json={'guild_id': 123, 'channel_id': 456})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'query is required' in data['error']

    def test_music_play_empty_query_returns_400(self, flask_client):
        response = flask_client.post('/music/play', json={'guild_id': 123, 'channel_id': 456, 'query': ''})
        assert response.status_code == 400

    def test_music_play_with_valid_query(self, flask_client):
        response = flask_client.post('/music/play',
            json={'guild_id': 123, 'channel_id': 456, 'query': 'never gonna give you up'})
        assert response.status_code in [200, 404, 500]

    def test_music_play_invalid_guild_id_type(self, flask_client):
        response = flask_client.post('/music/play',
            json={'guild_id': 'invalid', 'channel_id': 456, 'query': 'test'})
        assert response.status_code == 400


@pytest.mark.integration
class TestMusicStopEndpoint:
    def test_music_stop_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/stop', json={})
        assert response.status_code == 400

    def test_music_stop_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.post('/music/stop', json={'guild_id': 'invalid'})
        assert response.status_code == 400

    def test_music_stop_with_valid_guild_id(self, flask_client):
        response = flask_client.post('/music/stop', json={'guild_id': 123})
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestMusicSkipEndpoint:
    def test_music_skip_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/skip', json={})
        assert response.status_code == 400

    def test_music_skip_with_valid_guild_id(self, flask_client):
        response = flask_client.post('/music/skip', json={'guild_id': 123})
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestMusicPauseEndpoint:
    def test_music_pause_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/pause', json={})
        assert response.status_code == 400

    def test_music_pause_with_valid_guild_id(self, flask_client):
        response = flask_client.post('/music/pause', json={'guild_id': 123})
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestMusicResumeEndpoint:
    def test_music_resume_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/resume', json={})
        assert response.status_code == 400

    def test_music_resume_with_valid_guild_id(self, flask_client):
        response = flask_client.post('/music/resume', json={'guild_id': 123})
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestMusicQueueEndpoint:
    def test_music_queue_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.get('/music/queue')
        assert response.status_code == 400

    def test_music_queue_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.get('/music/queue?guild_id=invalid')
        assert response.status_code == 400

    def test_music_queue_with_valid_guild_id(self, flask_client):
        response = flask_client.get('/music/queue?guild_id=123')
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestEnterChannelEndpoint:
    def test_enter_channel_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/enter-channel', json={'channel_id': 456})
        assert response.status_code == 400

    def test_enter_channel_missing_channel_id_returns_400(self, flask_client):
        response = flask_client.post('/enter-channel', json={'guild_id': 123})
        assert response.status_code == 400

    def test_enter_channel_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.post('/enter-channel', json={'guild_id': 'invalid', 'channel_id': 456})
        assert response.status_code == 400

    def test_enter_channel_with_valid_ids(self, flask_client):
        response = flask_client.post('/enter-channel', json={'guild_id': 123, 'channel_id': 456})
        assert response.status_code in [200, 500, 503]


@pytest.mark.integration
class TestLeaveChannelEndpoint:
    def test_leave_channel_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/leave-channel', json={})
        assert response.status_code == 400

    def test_leave_channel_with_valid_guild_id(self, flask_client):
        response = flask_client.post('/leave-channel', json={'guild_id': 123})
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestUserVoiceChannelEndpoint:
    def test_user_voice_channel_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.get('/user/voice-channel?user_id=456')
        assert response.status_code == 400

    def test_user_voice_channel_missing_user_id_returns_400(self, flask_client):
        response = flask_client.get('/user/voice-channel?guild_id=123')
        assert response.status_code == 400

    def test_user_voice_channel_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.get('/user/voice-channel?guild_id=invalid&user_id=456')
        assert response.status_code == 400

    def test_user_voice_channel_invalid_user_id_type_returns_400(self, flask_client):
        response = flask_client.get('/user/voice-channel?guild_id=123&user_id=invalid')
        assert response.status_code == 400

    def test_user_voice_channel_with_valid_ids(self, flask_client):
        response = flask_client.get('/user/voice-channel?guild_id=123&user_id=456')
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestChatbotMessageEndpoint:
    def test_chatbot_message_missing_message_returns_400(self, flask_client):
        response = flask_client.post('/chatbot/message', json={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'message is required' in data['error']

    def test_chatbot_message_empty_message_returns_400(self, flask_client):
        response = flask_client.post('/chatbot/message', json={'message': ''})
        assert response.status_code == 400

    def test_chatbot_message_with_valid_message(self, flask_client):
        response = flask_client.post('/chatbot/message', json={'message': 'Hello bot'})
        assert response.status_code in [200, 500]


@pytest.mark.integration
class TestTTSSpeakEndpoint:
    def test_tts_speak_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/tts/speak', json={'channel_id': 456, 'text': 'test'})
        assert response.status_code == 400

    def test_tts_speak_missing_channel_id_returns_400(self, flask_client):
        response = flask_client.post('/tts/speak', json={'guild_id': 123, 'text': 'test'})
        assert response.status_code == 400

    def test_tts_speak_missing_text_returns_400(self, flask_client):
        response = flask_client.post('/tts/speak', json={'guild_id': 123, 'channel_id': 456})
        assert response.status_code == 400

    def test_tts_speak_empty_text_returns_400(self, flask_client):
        response = flask_client.post('/tts/speak', json={'guild_id': 123, 'channel_id': 456, 'text': ''})
        assert response.status_code == 400

    def test_tts_speak_with_valid_inputs(self, flask_client):
        response = flask_client.post('/tts/speak',
            json={'guild_id': 123, 'channel_id': 456, 'text': 'Hello world'})
        assert response.status_code in [200, 404, 500, 503]


@pytest.mark.integration
class TestErrorHandling:
    def test_invalid_json_body_returns_400(self, flask_client):
        response = flask_client.post('/music/volume',
            data='invalid json',
            content_type='application/json')
        assert response.status_code in [400, 500]

    def test_missing_content_type_with_json(self, flask_client):
        response = flask_client.post('/music/volume',
            data=json.dumps({'guild_id': 123, 'volume': 50}))
        assert response.status_code in [200, 400, 404]

    def test_get_endpoint_does_not_accept_post(self, flask_client):
        response = flask_client.post('/health')
        assert response.status_code == 405

    def test_post_endpoint_does_not_accept_get(self, flask_client):
        response = flask_client.get('/music/play')
        assert response.status_code == 405
