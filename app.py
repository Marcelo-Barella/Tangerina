import os
import logging
import asyncio
import threading
from typing import Optional, Dict, Any
import discord
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv

try:
    from features.music.spotify_integration import SpotifyIntegration
except ImportError:
    SpotifyIntegration = None

try:
    from elevenlabs import generate as tts_generate, set_api_key as set_eleven_api_key
except ImportError:
    tts_generate = None
    set_eleven_api_key = None

try:
    from chatbot.zhipu_integration import ZhipuChatbot
except ImportError:
    ZhipuChatbot = None

try:
    from chatbot.openai_integration import OpenAIChatbot
except ImportError:
    OpenAIChatbot = None

try:
    from chatbot.gemini_integration import GeminiChatbot
except ImportError:
    GeminiChatbot = None

try:
    from chatbot.memory_manager import MemoryManager
except ImportError:
    MemoryManager = None

try:
    from chatbot.web_search_service import TavilyWebSearchService
except ImportError:
    TavilyWebSearchService = None

try:
    from features.tts.piper_tts import PiperTTS
except ImportError:
    PiperTTS = None

try:
    from features.tts.http_tts import create_omnivoice_client
except ImportError:
    create_omnivoice_client = None

from features.music.music_bot import MusicBot, YTDLSource
from features.voice.voice_recv_patches import apply_voice_recv_patches
from features.music.music_service import MusicService, _resolve_voice_channel
from features.tts.tts_handler import speak_tts_unified
from flask_routes import create_flask_app
from features.discord.chatbot_reply import (
    post_chatbot_reply,
    should_respond_with_chatbot,
)

load_dotenv()
apply_voice_recv_patches()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not DISCORD_BOT_TOKEN:
    raise ValueError('DISCORD_BOT_TOKEN environment variable is required')


intents = Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot_loop: Optional[asyncio.AbstractEventLoop] = None

music_bot = MusicBot(bot)
music_bot.zhipu_api_key = os.getenv('ZHIPU_API_KEY')
_openai_api_key = (os.getenv('OPENAI_API_KEY') or '').strip()
music_bot.openai_api_key = _openai_api_key or None
music_bot.whisper_provider = os.getenv('WHISPER_PROVIDER') or ('openai-api' if _openai_api_key else 'sidecar')

spotify_client = None
if SpotifyIntegration and (SPOTIFY_CLIENT_ID := os.getenv('SPOTIFY_CLIENT_ID')) and (SPOTIFY_CLIENT_SECRET := os.getenv('SPOTIFY_CLIENT_SECRET')):
    try:
        spotify_client = SpotifyIntegration(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        logger.info("Spotify integration enabled")
    except Exception as e:
        logger.warning(f"Spotify integration disabled: {e}")

music_service = MusicService(bot, music_bot, spotify_client)
music_bot.music_service = music_service

memory_manager = None
if os.getenv('MEMORY_ENABLED', 'false').lower() == 'true' and MemoryManager:
    try:
        memory_manager = MemoryManager()
        if memory_manager._initialized:
            logger.info("MemoryManager initialized successfully")
        else:
            logger.warning("MemoryManager initialization failed, continuing without memory")
            memory_manager = None
    except Exception as e:
        logger.warning(f"MemoryManager disabled: {e}")

web_search_service = None
if os.getenv('WEB_SEARCH_ENABLED', 'true').lower() == 'true' and (TAVILY_API_KEY := os.getenv('TAVILY_API_KEY')) and TavilyWebSearchService:
    try:
        web_search_service = TavilyWebSearchService(TAVILY_API_KEY)
        logger.info("Web search service initialized")
    except Exception as e:
        logger.warning(f"Web search service disabled: {e}")

MODEL_PROVIDER = os.getenv('MODEL_PROVIDER', 'zhipu')
provider_map = {
    'openai': (OpenAIChatbot, _openai_api_key or None),
    'gemini': (GeminiChatbot, os.getenv('GEMINI_API_KEY')),
    'zhipu': (ZhipuChatbot, os.getenv('ZHIPU_API_KEY'))
}

chatbot = None
if MODEL_PROVIDER in provider_map and (ChatbotClass := provider_map[MODEL_PROVIDER][0]) and (api_key := provider_map[MODEL_PROVIDER][1]):
    try:
        chatbot = ChatbotClass(api_key, None, None, memory_manager, web_search_service)
        logger.info(f"{MODEL_PROVIDER.capitalize()} chatbot initialized")
    except Exception as e:
        logger.warning(f"{MODEL_PROVIDER.capitalize()} chatbot disabled: {e}")

tts_providers = {}
TTS_PROVIDER = os.getenv('TTS_PROVIDER', 'elevenlabs')
ELEVEN_API_KEY = os.getenv('ELEVEN_API_KEY')

if TTS_PROVIDER == 'elevenlabs' and ELEVEN_API_KEY and set_eleven_api_key:
    set_eleven_api_key(ELEVEN_API_KEY)
    tts_providers['elevenlabs'] = True
    logger.info("ElevenLabs TTS enabled")
elif TTS_PROVIDER == 'piper' and PiperTTS:
    try:
        tts_providers['piper'] = PiperTTS()
        logger.info("Piper TTS enabled")
    except Exception as e:
        logger.warning(f"Piper TTS disabled: {e}")
if create_omnivoice_client and (
    TTS_PROVIDER == 'omnivoice' or os.getenv('OMNIVOICE_API_URL')
):
    try:
        tts_providers['omnivoice'] = create_omnivoice_client()
        if TTS_PROVIDER == 'omnivoice':
            logger.info("OmniVoice TTS enabled")
        else:
            logger.info("OmniVoice TTS sidecar client enabled for /tts/omnivoice/speak")
    except Exception as e:
        logger.warning(f"OmniVoice TTS disabled: {e}")

music_bot.chatbot = chatbot
music_bot.tts_providers = tts_providers

async def speak_tts(guild_id: int, channel_id: int, text: str, provider: Optional[str] = None) -> Dict[str, Any]:
    return await speak_tts_unified(
        guild_id, channel_id, text, provider or TTS_PROVIDER, tts_providers,
        tts_generate, set_eleven_api_key, ELEVEN_API_KEY,
        "iP95p4xoKVk53GoZ742B", "eleven_multilingual_v2", "mp3_44100_128",
        music_bot, lambda gid, cid: _resolve_voice_channel(gid, cid, bot, music_bot),
        music_bot.ytdl, YTDLSource
    )

music_bot.speak_tts_func = speak_tts

flask_app, set_bot_loop = create_flask_app(
    bot, music_bot, music_service, chatbot, speak_tts, 'omnivoice' in tts_providers
)

@bot.event
async def on_ready() -> None:
    global bot_loop
    bot_loop = asyncio.get_running_loop()
    music_bot.main_loop = bot_loop
    set_bot_loop(bot_loop)
    logger.info(f'Bot connected as {bot.user}')
    
    if chatbot:
        chatbot.bot = bot
        chatbot.music_bot = music_bot
        logger.info(f"{MODEL_PROVIDER.capitalize()} chatbot configured")

@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    will_respond = bool(chatbot and should_respond_with_chatbot(message, bot.user))

    await bot.process_commands(message)

    try:
        if will_respond:
            guild_id = message.guild.id if message.guild else None
            channel_id = message.channel.id
            user_id = message.author.id

            music_functions = {
                "get_user_voice_channel": music_service.get_user_voice_channel,
                "play_music": music_service.play_music,
                "play_spotify_music": music_service.play_spotify_music,
                "stop_music": music_service.stop_music,
                "skip_music": music_service.skip_music,
                "pause_music": music_service.pause_music,
                "resume_music": music_service.resume_music,
                "set_volume": music_service.set_volume,
                "get_queue": music_service.get_queue,
                "leave_music": music_service.leave_music,
                "speak_tts": speak_tts,
            }

            retrieved_memories = {"recent": [], "semantic": []}
            if chatbot.memory_manager:
                retrieved_memories = await chatbot.memory_manager.retrieve_context(message.content, guild_id, channel_id, user_id)

            response, tool_calls = await chatbot.generate_response_with_tools(
                message.content, [], guild_id, channel_id, user_id, music_functions, retrieved_memories
            )

            if chatbot.memory_manager:
                await chatbot.memory_manager.store_conversation(message.content, response, guild_id, channel_id, user_id, tool_calls)

            await post_chatbot_reply(message.channel, response, tool_calls)

    except Exception as e:
        logger.error(f'Error processing message: {e}')

@bot.event
async def on_error(event: str, *args: Any, **kwargs: Any) -> None:
    logger.error(f'Discord event error in {event}: {args}, {kwargs}')

def run_flask() -> None:
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_discord() -> None:
    try:
        logger.info('Starting Discord bot...')
        bot.run(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Fatal error: {e}')

if not chatbot:
    logger.warning(f"{MODEL_PROVIDER.upper()}_API_KEY not set or chatbot unavailable")
if not tts_providers:
    logger.warning("No TTS provider configured")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info('Flask API started on http://0.0.0.0:5000')
    run_discord()
