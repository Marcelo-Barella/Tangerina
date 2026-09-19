import asyncio
import json
import os
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

@pytest.mark.integration
class TestMusicSkipEndpoint:
    def test_music_skip_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/skip', json={})
        assert response.status_code == 400

@pytest.mark.integration
class TestMusicPauseEndpoint:
    def test_music_pause_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/pause', json={})
        assert response.status_code == 400

@pytest.mark.integration
class TestMusicResumeEndpoint:
    def test_music_resume_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/music/resume', json={})
        assert response.status_code == 400

@pytest.mark.integration
class TestMusicQueueEndpoint:
    def test_music_queue_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.get('/music/queue')
        assert response.status_code == 400

    def test_music_queue_invalid_guild_id_type_returns_400(self, flask_client):
        response = flask_client.get('/music/queue?guild_id=invalid')
        assert response.status_code == 400

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

@pytest.mark.integration
class TestLeaveChannelEndpoint:
    def test_leave_channel_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/leave-channel', json={})
        assert response.status_code == 400

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

@pytest.mark.integration
class TestOmnivoiceSpeakEndpoint:
    def test_tts_omnivoice_speak_missing_guild_id_returns_400(self, flask_client):
        response = flask_client.post('/tts/omnivoice/speak', json={'channel_id': 456, 'text': 'test'})
        assert response.status_code == 400

    def test_tts_omnivoice_speak_missing_channel_id_returns_400(self, flask_client):
        response = flask_client.post('/tts/omnivoice/speak', json={'guild_id': 123, 'text': 'test'})
        assert response.status_code == 400

    def test_tts_omnivoice_speak_missing_text_returns_400(self, flask_client):
        response = flask_client.post('/tts/omnivoice/speak', json={'guild_id': 123, 'channel_id': 456})
        assert response.status_code == 400

    def test_tts_omnivoice_speak_empty_text_returns_400(self, flask_client):
        response = flask_client.post('/tts/omnivoice/speak', json={'guild_id': 123, 'channel_id': 456, 'text': ''})
        assert response.status_code == 400

    def test_tts_omnivoice_speak_timeout_returns_504(self, build_flask_test_app):
        app = build_flask_test_app(omnivoice_enabled=True)

        with patch('flask_routes.asyncio.run_coroutine_threadsafe') as mock_run:
            mock_future = MagicMock()
            mock_future.result.side_effect = TimeoutError()
            mock_run.return_value = mock_future

            with app.test_client() as client:
                response = client.post(
                    '/tts/omnivoice/speak',
                    json={'guild_id': 123, 'channel_id': 456, 'text': 'test'},
                )

        assert response.status_code == 504
        data = json.loads(response.data)
        assert 'timed out' in data['error'].lower()

@pytest.mark.integration
class TestVoicePreviewRoutes:
    def test_tts_preview_missing_text_returns_400(self, flask_client):
        response = flask_client.post('/tts/preview', json={})
        assert response.status_code == 400

    def test_tts_preview_unconfigured_provider_returns_503(self, flask_client):
        response = flask_client.post(
            '/tts/preview',
            json={'text': 'teste', 'provider': 'piper'},
        )
        assert response.status_code == 503

    def test_stt_transcribe_missing_file_returns_400(self, flask_client):
        response = flask_client.post('/stt/transcribe')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'file is required' in data['error']

    def test_tts_preview_returns_wav(self, build_flask_test_app):
        mock_piper = MagicMock()
        mock_piper.generate_speech.return_value = '/tmp/fake-preview.wav'
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with patch('flask_routes.send_file') as mock_send_file:
            mock_send_file.return_value = MagicMock(status_code=200)
            with app.test_client() as client:
                response = client.post('/tts/preview', json={'text': 'olá'})

        assert response.status_code == 200
        mock_piper.generate_speech.assert_called_once_with('olá')
        mock_send_file.assert_called_once()
        assert mock_send_file.call_args.args[0] == '/tmp/fake-preview.wav'
        assert mock_send_file.call_args.kwargs['mimetype'] == 'audio/wav'
        assert mock_send_file.call_args.kwargs['download_name'] == 'preview.wav'
        assert mock_send_file.call_args.kwargs['as_attachment'] is False

    def test_stt_transcribe_proxies_whisper(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'transcribed'}

        with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == 'transcribed'
        mock_post.assert_called_once()

    def test_tts_preview_rejects_elevenlabs(self, flask_client):
        response = flask_client.post(
            '/tts/preview',
            json={'text': 'teste', 'provider': 'ElevenLabs'},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'elevenlabs preview is not supported' in data['error']

    def test_tts_preview_generate_failure_returns_500(self, build_flask_test_app):
        mock_piper = MagicMock()
        mock_piper.generate_speech.side_effect = RuntimeError('piper down')
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with app.test_client() as client:
            response = client.post('/tts/preview', json={'text': 'olá'})

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['error'] == 'piper down'

    def test_stt_transcribe_timeout_returns_504(self, build_flask_test_app):
        import requests

        app = build_flask_test_app()

        with patch('flask_routes.requests.post', side_effect=requests.exceptions.Timeout()):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 504
        data = json.loads(response.data)
        assert 'timed out' in data['error'].lower()

    def test_stt_transcribe_sidecar_error_returns_502(self, build_flask_test_app):
        import requests

        app = build_flask_test_app()

        with patch(
            'flask_routes.requests.post',
            side_effect=requests.exceptions.ConnectionError('whisper down'),
        ):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 502
        data = json.loads(response.data)
        assert 'whisper down' in data['error']

    def test_stt_transcribe_non_json_sidecar_body_returns_502(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError('not json')

        with patch('flask_routes.requests.post', return_value=mock_response):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 502
        data = json.loads(response.data)
        assert 'Invalid JSON from Whisper sidecar' in data['error']

    def test_stt_transcribe_forwards_prompt_and_strips_text(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': '  Olá mundo  '}

        with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={
                        'file': (BytesIO(b'wav'), 'clip.wav'),
                        'prompt': '  Tangerina  ',
                    },
                    content_type='multipart/form-data',
                )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == 'Olá mundo'
        assert mock_post.call_args.kwargs['data'] == {'prompt': 'Tangerina'}

    def test_stt_transcribe_forwards_sidecar_http_error_json(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {'error': 'bad audio'}

        with patch('flask_routes.requests.post', return_value=mock_response):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 422
        data = json.loads(response.data)
        assert data['error'] == 'bad audio'

    def test_stt_transcribe_forwards_sidecar_http_error_text(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError('not json')
        mock_response.text = 'x' * 250

        with patch('flask_routes.requests.post', return_value=mock_response):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['error'] == 'x' * 200

    def test_stt_transcribe_uses_env_prompt_when_form_prompt_missing(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_INITIAL_PROMPT': '  Tangerina  '}):
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={'file': (BytesIO(b'wav'), 'audio.wav')},
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['data'] == {'prompt': 'Tangerina'}

    def test_tts_preview_disabled_provider_returns_503(self, build_flask_test_app):
        app = build_flask_test_app(tts_providers={'piper': None})

        with app.test_client() as client:
            response = client.post('/tts/preview', json={'text': 'olá'})

        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'not configured' in data['error']

    def test_tts_preview_cleans_up_generated_file(self, build_flask_test_app):
        from flask import Response

        mock_piper = MagicMock()
        mock_piper.generate_speech.return_value = '/tmp/fake-preview.wav'
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with patch(
            'flask_routes.send_file',
            return_value=Response(b'RIFF', mimetype='audio/wav'),
        ):
            with patch('flask_routes.cleanup_tts_file') as mock_cleanup:
                with app.test_client() as client:
                    response = client.post('/tts/preview', json={'text': 'olá'})

        assert response.status_code == 200
        mock_cleanup.assert_called_once_with('/tmp/fake-preview.wav')

    def test_stt_transcribe_omits_prompt_and_strips_whisper_url(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_API_URL': 'http://whisper.example:5002/'}):
            with patch('flask_routes.whisper_transcription_timeout', return_value=12.5):
                with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                    with app.test_client() as client:
                        response = client.post(
                            '/stt/transcribe',
                            data={'file': (BytesIO(b'wav'), 'audio.wav')},
                            content_type='multipart/form-data',
                        )

        assert response.status_code == 200
        mock_post.assert_called_once()
        assert mock_post.call_args.args[0] == 'http://whisper.example:5002/transcribe'
        assert mock_post.call_args.kwargs['timeout'] == 12.5
        assert mock_post.call_args.kwargs['data'] is None

    def test_stt_transcribe_missing_text_returns_empty_string(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch('flask_routes.requests.post', return_value=mock_response):
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': (BytesIO(b'wav'), 'audio.wav')},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['text'] == ''

    def test_tts_preview_empty_provider_defaults_to_piper(self, build_flask_test_app):
        mock_piper = MagicMock()
        mock_piper.generate_speech.return_value = '/tmp/fake-preview.wav'
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with patch('flask_routes.send_file') as mock_send_file:
            mock_send_file.return_value = MagicMock(status_code=200)
            with app.test_client() as client:
                response = client.post(
                    '/tts/preview',
                    json={'text': 'olá', 'provider': ''},
                )

        assert response.status_code == 200
        mock_piper.generate_speech.assert_called_once_with('olá')

    def test_tts_preview_normalizes_provider_case(self, build_flask_test_app):
        mock_piper = MagicMock()
        mock_piper.generate_speech.return_value = '/tmp/fake-preview.wav'
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with patch('flask_routes.send_file') as mock_send_file:
            mock_send_file.return_value = MagicMock(status_code=200)
            with app.test_client() as client:
                response = client.post(
                    '/tts/preview',
                    json={'text': 'olá', 'provider': 'PIPER'},
                )

        assert response.status_code == 200
        mock_piper.generate_speech.assert_called_once_with('olá')

    def test_tts_preview_uses_omnivoice_provider(self, build_flask_test_app):
        mock_omnivoice = MagicMock()
        mock_omnivoice.generate_speech.return_value = '/tmp/omni-preview.wav'
        app = build_flask_test_app(
            omnivoice_enabled=True,
            tts_providers={'omnivoice': mock_omnivoice},
        )

        with patch('flask_routes.send_file') as mock_send_file:
            mock_send_file.return_value = MagicMock(status_code=200)
            with app.test_client() as client:
                response = client.post(
                    '/tts/preview',
                    json={'text': 'olá', 'provider': 'omnivoice'},
                )

        assert response.status_code == 200
        mock_omnivoice.generate_speech.assert_called_once_with('olá')
        assert mock_send_file.call_args.args[0] == '/tmp/omni-preview.wav'

    def test_stt_transcribe_defaults_filename_and_mimetype(self, build_flask_test_app):
        from werkzeug.datastructures import FileStorage

        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}
        uploaded = FileStorage(stream=BytesIO(b'wav'), filename='', content_type='')

        with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
            with app.test_client() as client:
                response = client.post(
                    '/stt/transcribe',
                    data={'file': uploaded},
                    content_type='multipart/form-data',
                )

        assert response.status_code == 200
        files = mock_post.call_args.kwargs['files']
        assert files['file'][0] == 'audio.wav'
        assert files['file'][2] == 'audio/wav'

    def test_stt_transcribe_defaults_whisper_url_when_env_unset(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ'):
            os.environ.pop('WHISPER_API_URL', None)
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={'file': (BytesIO(b'wav'), 'audio.wav')},
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        mock_post.assert_called_once()
        assert mock_post.call_args.args[0] == 'http://whisper-asr:5002/transcribe'

    def test_stt_transcribe_whitespace_form_prompt_omits_data(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_INITIAL_PROMPT': 'Tangerina'}):
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={
                            'file': (BytesIO(b'wav'), 'audio.wav'),
                            'prompt': '   ',
                        },
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['data'] is None

    def test_stt_transcribe_whitespace_env_prompt_omits_data(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_INITIAL_PROMPT': '   '}):
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={'file': (BytesIO(b'wav'), 'audio.wav')},
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['data'] is None

    def test_tts_preview_generate_failure_skips_cleanup(self, build_flask_test_app):
        mock_piper = MagicMock()
        mock_piper.generate_speech.side_effect = RuntimeError('piper down')
        app = build_flask_test_app(tts_providers={'piper': mock_piper})

        with patch('flask_routes.cleanup_tts_file') as mock_cleanup:
            with app.test_client() as client:
                response = client.post('/tts/preview', json={'text': 'olá'})

        assert response.status_code == 500
        mock_cleanup.assert_not_called()

    def test_stt_transcribe_empty_form_prompt_uses_env(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_INITIAL_PROMPT': 'Tangerina'}):
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={
                            'file': (BytesIO(b'wav'), 'audio.wav'),
                            'prompt': '',
                        },
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['data'] == {'prompt': 'Tangerina'}

    def test_stt_transcribe_uses_default_timeout_when_env_unset(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ'):
            os.environ.pop('WHISPER_TRANSCRIPTION_TIMEOUT', None)
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={'file': (BytesIO(b'wav'), 'audio.wav')},
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['timeout'] == 30.0

    def test_stt_transcribe_uses_env_timeout_at_request_time(self, build_flask_test_app):
        app = build_flask_test_app()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'text': 'ok'}

        with patch.dict('os.environ', {'WHISPER_TRANSCRIPTION_TIMEOUT': '12.5'}):
            with patch('flask_routes.requests.post', return_value=mock_response) as mock_post:
                with app.test_client() as client:
                    response = client.post(
                        '/stt/transcribe',
                        data={'file': (BytesIO(b'wav'), 'audio.wav')},
                        content_type='multipart/form-data',
                    )

        assert response.status_code == 200
        assert mock_post.call_args.kwargs['timeout'] == 12.5


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
        assert response.status_code == 415

    def test_get_endpoint_does_not_accept_post(self, flask_client):
        response = flask_client.post('/health')
        assert response.status_code == 405

    def test_post_endpoint_does_not_accept_get(self, flask_client):
        response = flask_client.get('/music/play')
        assert response.status_code == 405
