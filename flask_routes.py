import asyncio
import logging
from flask import Flask, request, jsonify
from features.music.music_service import MusicService
from features.music.music_bot import MusicBot

logger = logging.getLogger(__name__)

VOLUME_MIN = 0
VOLUME_MAX = 100


def create_flask_app(bot, music_bot: MusicBot, music_service: MusicService, chatbot, speak_tts_func, speak_piper_tts_func):
    flask_app = Flask(__name__)
    bot_loop = None

    def require_bot_ready(f):
        def wrapper(*args, **kwargs):
            if not bot.is_ready() or not bot_loop:
                return jsonify({'error': 'Bot is not ready yet'}), 503
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper

    def parse_guild_id(request_data):
        try:
            return int(request_data.get('guild_id'))
        except (ValueError, TypeError):
            return None

    def parse_guild_channel_ids(request_data, require_channel=True):
        try:
            guild_id = int(request_data.get('guild_id'))
            channel_id = int(request_data.get('channel_id')) if require_channel else None
            return guild_id, channel_id
        except (ValueError, TypeError):
            return None, None

    def run_async(coro, timeout=10):
        future = asyncio.run_coroutine_threadsafe(coro, bot_loop)
        return future.result(timeout=timeout)

    @flask_app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'bot_ready': bot.is_ready()}), 200

    @flask_app.route('/enter-channel', methods=['POST'])
    @require_bot_ready
    def enter_channel():
        request_data = request.get_json() or {}
        guild_id, channel_id = parse_guild_channel_ids(request_data)
        if guild_id is None or channel_id is None:
            return jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        try:
            voice_client = run_async(music_bot.join_voice_channel(guild_id, channel_id))
            if voice_client:
                return jsonify({
                    'success': True,
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'channel_name': voice_client.channel.name if voice_client.channel else None
                }), 200
            return jsonify({'error': 'Failed to join voice channel'}), 500
        except RuntimeError as runtime_error:
            if 'PyNaCl' in str(runtime_error):
                return jsonify({'error': str(runtime_error), 'solution': 'pip install PyNaCl'}), 500
            raise

    @flask_app.route('/leave-channel', methods=['POST'])
    @require_bot_ready
    def leave_channel():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        leave_response = run_async(music_service.leave_music(guild_id))
        if leave_response.get('success'):
            return jsonify({'success': True, 'guild_id': guild_id}), 200
        return jsonify({'error': 'Bot was not in a voice channel'}), 404

    @flask_app.route('/user/voice-channel', methods=['GET'])
    @require_bot_ready
    def user_voice_channel():
        try:
            guild_id = int(request.args.get('guild_id'))
            user_id = int(request.args.get('user_id'))
        except (ValueError, TypeError):
            return jsonify({'error': 'guild_id and user_id must be integers'}), 400

        channel_response = run_async(music_service.get_user_voice_channel(guild_id, user_id))
        status_code = 200 if channel_response.get('success') else (404 if 'not found' in channel_response.get('error', '').lower() else 500)
        return jsonify(channel_response), status_code

    @flask_app.route('/music/play', methods=['POST'])
    @require_bot_ready
    def music_play():
        request_data = request.get_json() or {}
        guild_id, channel_id = parse_guild_channel_ids(request_data)
        if guild_id is None or channel_id is None:
            return jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        query = request_data.get('query')
        if not query:
            return jsonify({'error': 'query is required'}), 400

        play_response = run_async(music_service.play_music(guild_id, channel_id, query), timeout=30)
        return jsonify(play_response), 200 if play_response.get('success') else 500

    @flask_app.route('/music/stop', methods=['POST'])
    @require_bot_ready
    def music_stop():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        stop_response = run_async(music_service.stop_music(guild_id))
        return jsonify(stop_response), 200 if stop_response.get('success') else 404

    @flask_app.route('/music/skip', methods=['POST'])
    @require_bot_ready
    def music_skip():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        skip_response = run_async(music_service.skip_music(guild_id))
        return jsonify(skip_response), 200 if skip_response.get('success') else 404

    @flask_app.route('/music/pause', methods=['POST'])
    @require_bot_ready
    def music_pause():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        pause_response = run_async(music_service.pause_music(guild_id))
        return jsonify(pause_response), 200 if pause_response.get('success') else 404

    @flask_app.route('/music/resume', methods=['POST'])
    @require_bot_ready
    def music_resume():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        resume_response = run_async(music_service.resume_music(guild_id))
        return jsonify(resume_response), 200 if resume_response.get('success') else 404

    @flask_app.route('/music/volume', methods=['POST'])
    @require_bot_ready
    def music_volume():
        request_data = request.get_json() or {}
        try:
            guild_id = int(request_data.get('guild_id'))
            volume = int(request_data.get('volume'))
            if not VOLUME_MIN <= volume <= VOLUME_MAX:
                return jsonify({'error': 'volume must be between 0 and 100'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'guild_id and volume must be integers'}), 400

        volume_response = run_async(music_service.set_volume(guild_id, volume))
        return jsonify(volume_response), 200 if volume_response.get('success') else 404

    @flask_app.route('/music/queue', methods=['GET'])
    @require_bot_ready
    def music_queue():
        try:
            guild_id = int(request.args.get('guild_id'))
        except (ValueError, TypeError):
            return jsonify({'error': 'guild_id must be an integer'}), 400

        queue_response = run_async(music_service.get_queue(guild_id))
        return jsonify(queue_response), 200

    @flask_app.route('/music/spotify/play', methods=['POST'])
    @require_bot_ready
    def music_spotify_play():
        request_data = request.get_json() or {}
        guild_id, channel_id = parse_guild_channel_ids(request_data)
        if guild_id is None or channel_id is None:
            return jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        spotify_uri = request_data.get('spotify_uri')
        if not spotify_uri:
            return jsonify({'error': 'spotify_uri is required'}), 400

        spotify_response = run_async(music_service.play_spotify_music(guild_id, channel_id, spotify_uri), timeout=60)
        return jsonify(spotify_response), 200 if spotify_response.get('success') else 500

    @flask_app.route('/music/leave', methods=['POST'])
    @require_bot_ready
    def music_leave():
        request_data = request.get_json() or {}
        guild_id = parse_guild_id(request_data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        leave_response = run_async(music_service.leave_music(guild_id))
        return jsonify(leave_response), 200 if leave_response.get('success') else 404

    @flask_app.route('/tts/speak', methods=['POST'])
    @require_bot_ready
    def tts_speak():
        request_data = request.get_json() or {}
        guild_id, channel_id = parse_guild_channel_ids(request_data)
        if guild_id is None or channel_id is None:
            return jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        text = request_data.get('text')
        if not text:
            return jsonify({'error': 'text is required'}), 400

        tts_response = run_async(speak_tts_func(guild_id, channel_id, text), timeout=30)
        return jsonify(tts_response), 200 if tts_response.get('success') else 500

    @flask_app.route('/tts/piper/speak', methods=['POST'])
    @require_bot_ready
    def tts_piper_speak():
        request_data = request.get_json() or {}
        guild_id, channel_id = parse_guild_channel_ids(request_data)
        if guild_id is None or channel_id is None:
            return jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        text = request_data.get('text')
        if not text:
            return jsonify({'error': 'text is required'}), 400

        piper_response = run_async(speak_piper_tts_func(guild_id, channel_id, text), timeout=30)
        return jsonify(piper_response), 200 if piper_response.get('success') else 500

    @flask_app.route('/chatbot/message', methods=['POST'])
    @require_bot_ready
    def chatbot_message():
        if not chatbot:
            return jsonify({'error': 'Chatbot not configured'}), 503

        request_data = request.get_json() or {}
        message = request_data.get('message')
        if not message:
            return jsonify({'error': 'message is required'}), 400

        context = request_data.get('context', [])
        try:
            chatbot_response = run_async(chatbot.generate_response(message, context), timeout=30)
            return jsonify({'success': True, 'response': chatbot_response}), 200
        except Exception as chatbot_error:
            logger.error(f"Chatbot error: {chatbot_error}")
            return jsonify({'error': 'Chatbot processing failed'}), 500

    def set_bot_loop(loop):
        nonlocal bot_loop
        bot_loop = loop

    return flask_app, set_bot_loop
