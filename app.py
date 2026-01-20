import os
import logging
import asyncio
import threading
from typing import Optional, Dict, Any
import discord
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp

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

from features.music.music_bot import MusicBot, YTDLSource
from features.music.music_service import MusicService, _resolve_voice_channel
from features.tts.tts_handler import speak_tts_unified
from flask_routes import create_flask_app

load_dotenv()

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not DISCORD_BOT_TOKEN:
    raise ValueError('DISCORD_BOT_TOKEN environment variable is required')

N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')
if not N8N_WEBHOOK_URL:
    logger.warning('N8N_WEBHOOK_URL not set. n8n integration will be disabled.')

intents = Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot_loop: Optional[asyncio.AbstractEventLoop] = None

music_bot = MusicBot(bot)
music_bot.zhipu_api_key = os.getenv('ZHIPU_API_KEY')
music_bot.whisper_provider = os.getenv('WHISPER_PROVIDER', 'sidecar')
music_bot.openai_api_key = os.getenv('OPENAI_API_KEY')

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
    'openai': (OpenAIChatbot, os.getenv('OPENAI_API_KEY')),
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

music_bot.chatbot = chatbot
music_bot.tts_providers = tts_providers

async def speak_tts(guild_id: int, channel_id: int, text: str, provider: Optional[str] = None) -> Dict[str, Any]:
    async def resolve_channel(gid: int, cid: int) -> tuple[Optional[int], Optional[str]]:
        return await _resolve_voice_channel(gid, cid, bot, music_bot)
    return await speak_tts_unified(
        guild_id, channel_id, text, provider or TTS_PROVIDER, tts_providers,
        tts_generate, set_eleven_api_key, ELEVEN_API_KEY,
        "iP95p4xoKVk53GoZ742B", "eleven_multilingual_v2", "mp3_44100_128",
        music_bot, resolve_channel, music_bot.ytdl, YTDLSource
    )

async def speak_piper_tts(guild_id: int, channel_id: int, text: str) -> Dict[str, Any]:
    return await speak_tts(guild_id, channel_id, text, 'piper')

music_bot.speak_tts_func = speak_piper_tts

flask_app, set_bot_loop = create_flask_app(
    bot, music_bot, music_service, chatbot, speak_tts, speak_piper_tts
)

async def forward_to_n8n(msg_data: Dict[str, Any]) -> Optional[int]:
    if not N8N_WEBHOOK_URL:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_WEBHOOK_URL,
                json=msg_data,
                headers={'Content-Type': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                logger.info(f'Forwarded message to n8n, status: {response.status}')
                return response.status
    except asyncio.TimeoutError:
        logger.error('Timeout forwarding message to n8n')
        return None
    except Exception as e:
        logger.error(f'Error forwarding to n8n: {e}')
        return None

def extract_message_data(message: discord.Message) -> Dict[str, Any]:
    return {
        'content': message.content,
        'author': {
            'id': str(message.author.id),
            'name': message.author.name,
            'discriminator': message.author.discriminator,
            'bot': message.author.bot
        },
        'channel': {
            'id': str(message.channel.id),
            'name': getattr(message.channel, 'name', None)
        },
        'guild': {
            'id': str(message.guild.id) if message.guild else None,
            'name': message.guild.name if message.guild else None
        },
        'message_id': str(message.id),
        'timestamp': message.created_at.isoformat(),
        'embeds': [embed.to_dict() for embed in message.embeds],
        'attachments': [
            {'id': str(att.id), 'filename': att.filename, 'url': att.url, 'size': att.size}
            for att in message.attachments
        ]
    }


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

def should_respond_with_chatbot(message) -> bool:
    if message.author.bot:
        return False
    content = message.content.lower().strip()
    return 'tangerina' in content or (bot.user and bot.user.mentioned_in(message)) or message.guild is None

@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    await bot.process_commands(message)

    try:
        msg_data = extract_message_data(message)
        if chatbot and should_respond_with_chatbot(message):
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

            msg_data.update({'chatbot_response': response, 'tool_calls': tool_calls})

        if N8N_WEBHOOK_URL:
            await forward_to_n8n(msg_data)

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
