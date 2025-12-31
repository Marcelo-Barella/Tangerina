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

    def parse_guild_id(data):
        try:
            return int(data.get('guild_id'))
        except (ValueError, TypeError):
            return None

    def parse_guild_channel_ids(data, require_channel=True):
        guild_id = data.get('guild_id')
        channel_id = data.get('channel_id') if require_channel else None

        try:
            guild_id = int(guild_id)
            if require_channel:
                channel_id = int(channel_id)
        except (ValueError, TypeError):
            return None, None, jsonify({'error': 'guild_id and channel_id must be integers'}), 400

        return guild_id, channel_id, None, None

    def run_async(coro, timeout=10):
        future = asyncio.run_coroutine_threadsafe(coro, bot_loop)
        return future.result(timeout=timeout)

    @flask_app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'bot_ready': bot.is_ready()}), 200

    @flask_app.route('/enter-channel', methods=['POST'])
    @require_bot_ready
    def enter_channel():
        data = request.get_json() or {}
        guild_id, channel_id, err, code = parse_guild_channel_ids(data)
        if err:
            return err, code

        try:
            vc = run_async(music_bot.join_voice_channel(guild_id, channel_id))
            if vc:
                return jsonify({
                    'success': True,
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'channel_name': vc.channel.name if vc.channel else None
                }), 200
            return jsonify({'error': 'Failed to join voice channel'}), 500
        except RuntimeError as e:
            if 'PyNaCl' in str(e):
                return jsonify({'error': str(e), 'solution': 'pip install PyNaCl'}), 500
            raise

    @flask_app.route('/leave-channel', methods=['POST'])
    @require_bot_ready
    def leave_channel():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        success = run_async(music_service.leave_music(guild_id))
        if success.get('success'):
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

        result = run_async(music_service.get_user_voice_channel(guild_id, user_id))
        status = 200 if result.get('success') else (404 if 'not found' in result.get('error', '').lower() else 500)
        return jsonify(result), status

    @flask_app.route('/music/play', methods=['POST'])
    @require_bot_ready
    def music_play():
        data = request.get_json() or {}
        guild_id, channel_id, err, code = parse_guild_channel_ids(data)
        if err:
            return err, code

        query = data.get('query')
        if not query:
            return jsonify({'error': 'query is required'}), 400

        result = run_async(music_service.play_music(guild_id, channel_id, query), timeout=30)
        return jsonify(result), 200 if result.get('success') else 500

    @flask_app.route('/music/stop', methods=['POST'])
    @require_bot_ready
    def music_stop():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.stop_music(guild_id))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/music/skip', methods=['POST'])
    @require_bot_ready
    def music_skip():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.skip_music(guild_id))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/music/pause', methods=['POST'])
    @require_bot_ready
    def music_pause():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.pause_music(guild_id))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/music/resume', methods=['POST'])
    @require_bot_ready
    def music_resume():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.resume_music(guild_id))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/music/volume', methods=['POST'])
    @require_bot_ready
    def music_volume():
        data = request.get_json() or {}
        try:
            guild_id = int(data.get('guild_id'))
            volume = int(data.get('volume'))
            if not VOLUME_MIN <= volume <= VOLUME_MAX:
                return jsonify({'error': 'volume must be between 0 and 100'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'guild_id and volume must be integers'}), 400

        result = run_async(music_service.set_volume(guild_id, volume))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/music/queue', methods=['GET'])
    @require_bot_ready
    def music_queue():
        try:
            guild_id = int(request.args.get('guild_id'))
        except (ValueError, TypeError):
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.get_queue(guild_id))
        return jsonify(result), 200

    @flask_app.route('/music/spotify/play', methods=['POST'])
    @require_bot_ready
    def music_spotify_play():
        data = request.get_json() or {}
        guild_id, channel_id, err, code = parse_guild_channel_ids(data)
        if err:
            return err, code

        spotify_uri = data.get('spotify_uri')
        if not spotify_uri:
            return jsonify({'error': 'spotify_uri is required'}), 400

        result = run_async(music_service.play_spotify_music(guild_id, channel_id, spotify_uri), timeout=60)
        return jsonify(result), 200 if result.get('success') else 500

    @flask_app.route('/music/leave', methods=['POST'])
    @require_bot_ready
    def music_leave():
        data = request.get_json() or {}
        guild_id = parse_guild_id(data)
        if guild_id is None:
            return jsonify({'error': 'guild_id must be an integer'}), 400

        result = run_async(music_service.leave_music(guild_id))
        return jsonify(result), 200 if result.get('success') else 404

    @flask_app.route('/tts/speak', methods=['POST'])
    @require_bot_ready
    def tts_speak():
        data = request.get_json() or {}
        guild_id, channel_id, err, code = parse_guild_channel_ids(data)
        if err:
            return err, code

        text = data.get('text')
        if not text:
            return jsonify({'error': 'text is required'}), 400

        result = run_async(speak_tts_func(guild_id, channel_id, text), timeout=30)
        return jsonify(result), 200 if result.get('success') else 500

    @flask_app.route('/tts/piper/speak', methods=['POST'])
    @require_bot_ready
    def tts_piper_speak():
        data = request.get_json() or {}
        guild_id, channel_id, err, code = parse_guild_channel_ids(data)
        if err:
            return err, code

        text = data.get('text')
        if not text:
            return jsonify({'error': 'text is required'}), 400

        result = run_async(speak_piper_tts_func(guild_id, channel_id, text), timeout=30)
        return jsonify(result), 200 if result.get('success') else 500

    @flask_app.route('/chatbot/message', methods=['POST'])
    @require_bot_ready
    def chatbot_message():
        if not chatbot:
            return jsonify({'error': 'Chatbot not configured'}), 503

        data = request.get_json() or {}
        message = data.get('message')
        if not message:
            return jsonify({'error': 'message is required'}), 400

        context = data.get('context', [])
        try:
            response = run_async(chatbot.generate_response(message, context), timeout=30)
            return jsonify({'success': True, 'response': response}), 200
        except Exception as e:
            logger.error(f"Chatbot error: {e}")
            return jsonify({'error': 'Chatbot processing failed'}), 500

    def set_bot_loop(loop):
        nonlocal bot_loop
        bot_loop = loop

    return flask_app, set_bot_loop
