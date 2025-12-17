import os
import logging
import asyncio
import threading
import re
from typing import Optional, Dict, Any, Tuple
import discord
from discord import Intents
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp
from flask import Flask, request, jsonify
import tempfile
import yt_dlp
from collections import deque
import io
import wave
import subprocess
import time

try:
    from spotify_integration import SpotifyIntegration
except ImportError:
    SpotifyIntegration = None


try:
    from elevenlabs import generate as tts_generate, set_api_key as set_eleven_api_key
except ImportError:
    tts_generate = None
    set_eleven_api_key = None

try:
    from zhipu_integration import ZhipuChatbot
except ImportError:
    ZhipuChatbot = None

try:
    from piper_tts import PiperTTS
except ImportError:
    PiperTTS = None

try:
    import nacl
except ImportError:
    nacl = None

try:
    from discord.ext import voice_recv
except ImportError:
    voice_recv = None

load_dotenv()

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY')
TTS_PROVIDER = os.getenv('TTS_PROVIDER', 'elevenlabs')
ELEVEN_API_KEY = os.getenv('ELEVEN_API_KEY')

if not DISCORD_BOT_TOKEN:
    raise ValueError('DISCORD_BOT_TOKEN environment variable is required')

if not N8N_WEBHOOK_URL:
    logger.warning('N8N_WEBHOOK_URL not set. n8n integration will be disabled.')

intents = Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot_loop: Optional[asyncio.AbstractEventLoop] = None

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extractaudio': True,
    'audioformat': 'best',
    'prefer_ffmpeg': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

MIN_AUDIO_CHUNKS = 10
ELEVEN_VOICE_ID = "iP95p4xoKVk53GoZ742B"
ELEVEN_MODEL = "eleven_multilingual_v2"
ELEVEN_OUTPUT_FORMAT = "mp3_44100_128"
ELEVEN_CLEANUP_DELAY = 20
PIPER_CLEANUP_DELAY = 5
QUEUE_DISPLAY_LIMIT = 5
VOLUME_MIN = 0
VOLUME_MAX = 100


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        logger.info(f"Creating audio source for: {data.get('title', 'Unknown')}")

        try:
            return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)
        except discord.errors.ClientException as e:
            if "ffmpeg" in str(e).lower():
                raise Exception("FFmpeg não está instalado. Instale o FFmpeg para usar a funcionalidade de música.")
            raise

    @classmethod
    async def search_youtube(cls, query: str) -> Optional[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        search_query = f"ytsearch1:{query}"

        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))

            if data and 'entries' in data and data['entries']:
                entry = data['entries'][0]
                entry['url'] = entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                return entry
        except Exception as e:
            logger.error(f"YouTube search failed for '{query}': {e}")
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
                if data and 'entries' in data and data['entries']:
                    return data['entries'][0]
                if data and 'title' in data:
                    return data
            except Exception:
                pass

        return None


class MusicBot:
    def __init__(self):
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.queues: Dict[int, list] = {}
        self.current_songs: Dict[int, dict] = {}
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        self.voice_sinks: Dict[int, 'VoiceCommandSink'] = {}
        self.original_volumes: Dict[int, float] = {}

    def _check_nacl(self):
        if nacl is None:
            raise RuntimeError("PyNaCl library needed for voice. Install with: pip install PyNaCl")

    def _get_existing_voice_client(self, guild_id: int, channel_id: int) -> Optional[discord.VoiceClient]:
        for vc in bot.voice_clients:
            if vc.guild.id == guild_id and vc.is_connected():
                if vc.channel and vc.channel.id == channel_id:
                    if guild_id not in self.voice_clients:
                        self.voice_clients[guild_id] = vc
                    return vc
        return None

    def _get_current_voice_channel(self, guild_id: int) -> Optional[discord.VoiceClient]:
        for vc in bot.voice_clients:
            if vc.guild.id == guild_id and vc.is_connected() and vc.channel:
                if guild_id not in self.voice_clients:
                    self.voice_clients[guild_id] = vc
                return vc
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_connected() and vc.channel:
                return vc
        return None

    async def _move_or_connect(self, guild_id: int, channel) -> Optional[discord.VoiceClient]:
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_connected():
                if vc.channel and vc.channel.id != channel.id:
                    await vc.move_to(channel)
                return vc
            del self.voice_clients[guild_id]

        if voice_recv:
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
            self.voice_clients[guild_id] = vc
            if guild_id not in self.voice_sinks:
                sink = VoiceCommandSink(bot, vc, guild_id)
                if hasattr(vc, 'start_listening'):
                    vc.start_listening(sink)
                self.voice_sinks[guild_id] = sink
        else:
            vc = await channel.connect()
            self.voice_clients[guild_id] = vc

        return vc

    async def join_voice_channel(self, guild_id: int, channel_id: int) -> Optional[discord.VoiceClient]:
        self._check_nacl()

        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error(f'Guild {guild_id} not found')
            return None

        channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(channel_id)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException) as e:
                logger.error(f'Voice channel {channel_id} not found or inaccessible: {e}')
                return None
        
        if not channel or not hasattr(channel, 'connect'):
            logger.error(f'Channel {channel_id} is not a voice channel or cannot be connected to')
            return None

        existing = self._get_existing_voice_client(guild_id, channel_id)
        if existing:
            return existing

        try:
            return await self._move_or_connect(guild_id, channel)
        except discord.errors.ClientException as e:
            if 'already connected' in str(e).lower():
                return self._get_existing_voice_client(guild_id, channel_id)
            if 'pynacl' in str(e).lower() or 'nacl' in str(e).lower():
                raise RuntimeError("PyNaCl library needed for voice. Install with: pip install PyNaCl") from e
            raise
        except Exception as e:
            logger.error(f'Error joining voice channel: {e}')
            return None

    async def play_next(self, guild_id: int):
        if guild_id not in self.queues or not self.queues[guild_id]:
            return
        if guild_id not in self.voice_clients:
            return

        voice_client = self.voice_clients[guild_id]
        next_song = self.queues[guild_id].pop(0)

        try:
            if next_song.get('source') == 'spotify':
                next_song = await self._resolve_spotify_track(next_song, guild_id)
                if not next_song:
                    await self.play_next(guild_id)
                    return

            player = await YTDLSource.from_url(next_song['url'], stream=True)
            loop = self.main_loop or asyncio.get_running_loop()
            voice_client.play(
                player,
                after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, self.play_next(guild_id)),
            )
            self.current_songs[guild_id] = next_song
        except Exception as e:
            logger.error(f"Error playing next song: {e}")
            await self.play_next(guild_id)

    async def _resolve_spotify_track(self, song_data: dict, guild_id: int) -> Optional[dict]:
        spotify_track = song_data.get('spotify_track')
        if not spotify_track or not spotify_client:
            return None

        youtube_query = spotify_client.track_to_youtube_query(spotify_track)
        if not youtube_query:
            return None

        return await YTDLSource.search_youtube(youtube_query)

    def get_current_music_source(self, guild_id: int) -> Optional[Dict[str, Any]]:
        if guild_id not in self.voice_clients:
            return None
        
        voice_client = self.voice_clients[guild_id]
        is_connected = voice_client.is_connected()
        is_playing = voice_client.is_playing()
        if not is_connected or not is_playing:
            return None
        
        current_song = self.current_songs.get(guild_id)
        if not current_song:
            return None
        
        current_volume = 0.5
        if voice_client.source and isinstance(voice_client.source, discord.PCMVolumeTransformer):
            current_volume = voice_client.source.volume
        
        result = {
            'url': current_song.get('url'),
            'title': current_song.get('title', 'Unknown'),
            'volume': current_volume,
            'is_playing': True
        }
        return result


class VoiceCommandSink(voice_recv.AudioSink):
    VOICE_COMMANDS = {
        'play': ['toca', 'play', 'tocar'],
        'stop': ['para', 'stop', 'parar'],
        'skip': ['pula', 'skip', 'pular'],
        'pause': ['pausa', 'pause', 'pausar'],
        'resume': ['continua', 'resume', 'continuar'],
        'queue': ['fila', 'queue', 'fila de música'],
        'leave': ['sai', 'leave', 'sair'],
        'chat': ['tangerina', 'fala', 'conversa', 'chat'],
    }

    def __init__(self, bot_instance, voice_client, guild_id: int):
        super().__init__()
        self.bot = bot_instance
        self._voice_client = voice_client
        self.guild_id = guild_id
        self.audio_buffers: Dict[int, deque] = {}
        self.speaking_users = set()
        self.zhipu_api_key = ZHIPU_API_KEY

        if not self.zhipu_api_key:
            logger.warning("ZHIPU_API_KEY not set. GLM-ASR-2512 voice transcription unavailable.")

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data: voice_recv.VoiceData):
        if user is None:
            return

        if user.id not in self.audio_buffers:
            self.audio_buffers[user.id] = deque(maxlen=150)

        if data.pcm:
            self.audio_buffers[user.id].append(data.pcm)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member):
        self.speaking_users.add(member.id)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member):
        if member.id in self.speaking_users:
            self.speaking_users.remove(member.id)
            asyncio.create_task(self.process_speech(member))

    async def process_speech(self, member):
        if member.id not in self.audio_buffers:
            return

        audio_chunks = list(self.audio_buffers[member.id])
        self.audio_buffers[member.id].clear()

        if len(audio_chunks) < MIN_AUDIO_CHUNKS:
            return

        try:
            audio_data = self._combine_audio_chunks(audio_chunks)
            text = await self._transcribe_audio(audio_data)

            if text and text.strip():
                logger.info(f"Transcribed from {member.display_name}: {text}")
                await self._handle_voice_command(member, text.strip())
        except Exception as e:
            logger.error(f"Error processing speech from {member.display_name}: {e}")

    def _combine_audio_chunks(self, chunks):
        combined = b''.join(chunks)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(combined)
        wav_buffer.seek(0)
        return wav_buffer

    async def _transcribe_audio(self, audio_data):
        if not self.zhipu_api_key:
            return None

        try:
            audio_data.seek(0)
            audio_bytes = audio_data.read()
            
            url = "https://api.z.ai/api/paas/v4/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.zhipu_api_key}"
            }
            
            data = aiohttp.FormData()
            data.add_field('model', 'glm-asr-2512')
            data.add_field('stream', 'false')
            data.add_field('file', 
                          audio_bytes,
                          filename='audio.wav',
                          content_type='audio/wav')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('text', '')
                        return text if text else None
                    else:
                        error_text = await response.text()
                        logger.error(f"GLM-ASR-2512 transcription error: HTTP {response.status} - {error_text}")
                        return None
        except asyncio.TimeoutError:
            logger.error("GLM-ASR-2512 transcription timeout")
            return None
        except Exception as e:
            logger.error(f"GLM-ASR-2512 transcription error: {e}")
            return None

    async def _handle_voice_command(self, member, text: str):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return

        text_channel = next(
            (ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages),
            None
        )
        if not text_channel:
            return

        text_lower = text.lower().strip()

        command_handlers = {
            'play': self._handle_play,
            'stop': self._handle_stop,
            'skip': self._handle_skip,
            'pause': self._handle_pause,
            'resume': self._handle_resume,
            'queue': self._handle_queue,
            'leave': self._handle_leave,
            'chat': self._handle_chat,
        }

        for cmd, keywords in self.VOICE_COMMANDS.items():
            if any(word in text_lower for word in keywords):
                await command_handlers[cmd](text_channel, text_lower)
                return

        if 'volume' in text_lower:
            await self._handle_volume(text_channel, text_lower)
            return

        await text_channel.send(f"Comando não reconhecido: {text}")

    async def _handle_play(self, channel, text):
        query = re.sub(r'\b(toca|play|tocar)\b', '', text).strip()
        if query:
            try:
                result = await play_music(self.guild_id, channel.id, query)
                await channel.send(result.get('message', 'Comando executado'))
            except Exception as e:
                logger.error(f"Error executing play command: {e}")
                await channel.send("Erro ao tocar música")

    async def _handle_stop(self, channel, _):
        result = await stop_music(self.guild_id)
        await channel.send(result.get('message', 'Música parada'))

    async def _handle_skip(self, channel, _):
        result = await skip_music(self.guild_id)
        await channel.send(result.get('message', 'Música pulada'))

    async def _handle_pause(self, channel, _):
        result = await pause_music(self.guild_id)
        await channel.send(result.get('message', 'Música pausada'))

    async def _handle_resume(self, channel, _):
        result = await resume_music(self.guild_id)
        await channel.send(result.get('message', 'Música retomada'))

    async def _handle_queue(self, channel, _):
        result = await get_queue(self.guild_id)
        queue = result.get('queue', [])
        if queue:
            queue_text = "\n".join([f"{i+1}. {song.get('title', 'Unknown')}" for i, song in enumerate(queue[:QUEUE_DISPLAY_LIMIT])])
            await channel.send(f"Fila:\n```{queue_text}```")
        else:
            await channel.send("Fila vazia")

    async def _handle_leave(self, channel, _):
        result = await leave_music(self.guild_id)
        await channel.send(result.get('message', 'Saindo do canal'))

    async def _handle_volume(self, channel, text):
        volume_match = re.search(r'\d+', text)
        if volume_match:
            volume = int(volume_match.group())
            if VOLUME_MIN <= volume <= VOLUME_MAX:
                result = await set_volume(self.guild_id, volume)
                await channel.send(result.get('message', f'Volume ajustado para {volume}%'))

    async def _handle_chat(self, channel, text):
        if not chatbot:
            await channel.send("Chatbot não está configurado")
            return

        chat_text = re.sub(r'\b(tangerina|fala|conversa|chat)\b', '', text).strip()
        if not chat_text:
            await channel.send("O que você gostaria de conversar?")
            return

        try:
            response = await chatbot.generate_response(chat_text)
            await channel.send(response)

            if 'piper' in tts_providers and tts_providers['piper']:
                voice_client = music_bot.voice_clients.get(self.guild_id)
                if voice_client and voice_client.is_connected():
                    await speak_piper_tts(self.guild_id, voice_client.channel.id, response)
        except Exception as e:
            logger.error(f"Chatbot error: {e}")
            await channel.send("Erro no chatbot")

    def cleanup(self):
        self.audio_buffers.clear()
        self.speaking_users.clear()


music_bot = MusicBot()

spotify_client = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SpotifyIntegration:
    try:
        spotify_client = SpotifyIntegration(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        logger.info("Spotify integration enabled")
    except Exception as e:
        logger.warning(f"Spotify integration disabled: {e}")

chatbot = None
if ZHIPU_API_KEY and ZhipuChatbot:
    try:
        chatbot = ZhipuChatbot(ZHIPU_API_KEY, bot_instance=None, music_bot_instance=None)
        logger.info("ZhipuAI GLM chatbot initialized (will be configured with bot instances after bot is ready)")
    except Exception as e:
        logger.warning(f"ZhipuAI chatbot disabled: {e}")

tts_providers = {}
if TTS_PROVIDER == 'elevenlabs' and ELEVEN_API_KEY and set_eleven_api_key:
    set_eleven_api_key(ELEVEN_API_KEY)
    tts_providers['elevenlabs'] = True
    logger.info("ElevenLabs TTS enabled")

if TTS_PROVIDER == 'piper' and PiperTTS:
    try:
        tts_providers['piper'] = PiperTTS()
        logger.info("Piper TTS enabled")
    except Exception as e:
        logger.warning(f"Piper TTS disabled: {e}")

flask_app = Flask(__name__)


async def forward_to_n8n(message_data: dict):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_WEBHOOK_URL,
                json=message_data,
                headers={'Content-Type': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                logger.info(f'Forwarded message to n8n, status: {response.status}')
                return response.status
    except asyncio.TimeoutError:
        logger.error('Timeout forwarding message to n8n')
    except Exception as e:
        logger.error(f'Error forwarding to n8n: {e}')
    return None


def extract_message_data(message) -> dict:
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


async def _resolve_voice_channel(guild_id: int, channel_id: int) -> Tuple[Optional[int], Optional[str]]:
    guild = bot.get_guild(guild_id)
    if not guild:
        return None, f'Guild {guild_id} not found'
    
    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            pass
    
    if channel and not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        current_vc = music_bot._get_current_voice_channel(guild_id)
        if current_vc and current_vc.channel:
            channel_id = current_vc.channel.id
            logger.info(f'Using bot\'s current voice channel {channel_id} instead of text channel {channel.id}')
        else:
            return None, f'Channel {channel_id} is a text channel. Please specify a voice channel or use EnterChannel first.'
    
    return channel_id, None


async def get_user_voice_channel(guild_id: int, user_id: int) -> Dict[str, Any]:
    guild = bot.get_guild(guild_id)
    if not guild:
        return {'success': False, 'error': f'Guild {guild_id} not found'}

    member = guild.get_member(user_id)
    if not member:
        return {'success': False, 'error': f'User {user_id} not found'}

    if not member.voice or not member.voice.channel:
        return {'success': True, 'in_voice_channel': False, 'channel_id': None, 'channel_name': None}

    channel = member.voice.channel
    return {
        'success': True,
        'in_voice_channel': True,
        'guild_id': guild_id,
        'user_id': user_id,
        'channel_id': channel.id,
        'channel_name': channel.name
    }


async def play_spotify_music(guild_id: int, channel_id: int, spotify_uri: str) -> Dict[str, Any]:
    if not spotify_client:
        return {'success': False, 'error': 'Spotify integration not configured'}

    parsed = spotify_client.parse_uri(spotify_uri)
    if not parsed:
        return {'success': False, 'error': 'Invalid Spotify URI'}

    uri_type = parsed['type']
    tracks = []

    if uri_type == 'track':
        track_info = spotify_client.get_track_info(spotify_uri)
        if track_info:
            tracks = [track_info]
    elif uri_type == 'playlist':
        tracks = spotify_client.get_playlist_tracks(spotify_uri)
    elif uri_type == 'album':
        tracks = spotify_client.get_album_tracks(spotify_uri)
    else:
        return {'success': False, 'error': f'Unsupported type: {uri_type}'}

    if not tracks:
        return {'success': False, 'error': 'No tracks found'}

    resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id)
    if error:
        return {'success': False, 'error': error}
    
    voice_client = await music_bot.join_voice_channel(guild_id, resolved_channel_id)
    if not voice_client:
        return {'success': False, 'error': 'Failed to join voice channel'}

    if guild_id not in music_bot.queues:
        music_bot.queues[guild_id] = []

    for track in tracks:
        music_bot.queues[guild_id].append({
            'source': 'spotify',
            'spotify_track': track,
            'title': track.get('name', 'Unknown'),
            'artists': [artist.get('name', '') for artist in track.get('artists', [])]
        })

    if not voice_client.is_playing():
        await music_bot.play_next(guild_id)
        current = music_bot.current_songs.get(guild_id)
        return {
            'success': True,
            'tracks_queued': len(tracks),
            'message': f"Now playing: {current.get('title', 'Unknown') if current else 'Unknown'}"
        }

    return {'success': True, 'tracks_queued': len(tracks), 'message': f"Added {len(tracks)} track(s) to queue"}


async def play_music(guild_id: int, channel_id: int, query: str) -> Dict[str, Any]:
    if spotify_client:
        spotify_patterns = [r'spotify:(track|playlist|album|artist):', r'open\.spotify\.com/(track|playlist|album|artist)/']
        if any(re.search(pattern, query) for pattern in spotify_patterns):
            return await play_spotify_music(guild_id, channel_id, query)

    resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id)
    if error:
        return {'success': False, 'error': error}
    
    voice_client = await music_bot.join_voice_channel(guild_id, resolved_channel_id)
    if not voice_client:
        return {'success': False, 'error': 'Failed to join voice channel'}

    song_data = await YTDLSource.search_youtube(query)
    if not song_data:
        return {'success': False, 'error': f'No results found for: {query}'}

    if guild_id not in music_bot.queues:
        music_bot.queues[guild_id] = []

    if voice_client.is_playing():
        music_bot.queues[guild_id].append(song_data)
        return {'success': True, 'song': song_data, 'queued': True, 'message': f"Added '{song_data['title']}' to queue"}

    player = await YTDLSource.from_url(song_data['url'], stream=True)
    loop = music_bot.main_loop or asyncio.get_running_loop()
    voice_client.play(
        player,
        after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, music_bot.play_next(guild_id)),
    )
    music_bot.current_songs[guild_id] = song_data
    return {'success': True, 'song': song_data, 'queued': False, 'message': f"Now playing: {song_data['title']}"}


async def stop_music(guild_id: int) -> Dict[str, Any]:
    if guild_id not in music_bot.voice_clients:
        return {'success': False, 'error': 'Bot not in voice channel'}

    music_bot.voice_clients[guild_id].stop()
    music_bot.queues[guild_id] = []
    return {'success': True, 'message': 'Music stopped and queue cleared'}


async def skip_music(guild_id: int) -> Dict[str, Any]:
    if guild_id in music_bot.voice_clients and music_bot.voice_clients[guild_id].is_playing():
        music_bot.voice_clients[guild_id].stop()
        return {'success': True, 'message': 'Skipped current song'}
    return {'success': False, 'error': 'No music playing'}


async def pause_music(guild_id: int) -> Dict[str, Any]:
    if guild_id in music_bot.voice_clients and music_bot.voice_clients[guild_id].is_playing():
        music_bot.voice_clients[guild_id].pause()
        return {'success': True, 'message': 'Music paused'}
    return {'success': False, 'error': 'No music playing'}


async def resume_music(guild_id: int) -> Dict[str, Any]:
    if guild_id in music_bot.voice_clients and music_bot.voice_clients[guild_id].is_paused():
        music_bot.voice_clients[guild_id].resume()
        return {'success': True, 'message': 'Music resumed'}
    return {'success': False, 'error': 'Music not paused'}


async def set_volume(guild_id: int, volume: int) -> Dict[str, Any]:
    if guild_id not in music_bot.voice_clients:
        return {'success': False, 'error': 'Bot not in voice channel'}

    vc = music_bot.voice_clients[guild_id]
    if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = volume / 100
        return {'success': True, 'volume': volume, 'message': f'Volume set to {volume}%'}
    return {'success': False, 'error': 'Cannot adjust volume'}


async def get_queue(guild_id: int) -> Dict[str, Any]:
    return {
        'queue': music_bot.queues.get(guild_id, []),
        'current': music_bot.current_songs.get(guild_id)
    }


class MixedAudioSource(discord.AudioSource):
    FRAME_SIZE = 3840
    
    def __init__(self, music_url: str, tts_file: str, music_volume: float = 0.2):
        self.music_url = music_url
        self.tts_file = tts_file
        self.music_volume = music_volume
        self.process = None
        
        filter_complex = f'[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_volume}[a0];[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0'
        
        cmd = [
            'ffmpeg',
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', music_url,
            '-i', tts_file,
            '-filter_complex', filter_complex,
            '-f', 's16le',
            '-ar', '48000',
            '-ac', '2',
            '-loglevel', 'warning',
            '-'
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(0.2)
            if self.process.poll() is not None:
                stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore') if self.process.stderr else ''
                logger.error(f"MixedAudioSource FFmpeg process died immediately: {stderr_output}")
                raise Exception(f"FFmpeg process died immediately with return code {self.process.returncode}: {stderr_output[:500]}")
            else:
                logger.info(f"MixedAudioSource FFmpeg process started successfully (PID: {self.process.pid}, music_url: {music_url[:80]}...)")
        except Exception as e:
            logger.error(f"Error starting FFmpeg process for audio mixing: {e}")
            raise
    
    def read(self):
        if self.process is None:
            return b''
        
        try:
            ret = self.process.stdout.read(self.FRAME_SIZE)
            if len(ret) != self.FRAME_SIZE:
                return b''
            return ret
        except Exception as e:
            logger.error(f"Error reading from FFmpeg process: {e}")
            return b''
    
    def cleanup(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.error(f"Error cleaning up FFmpeg process: {e}")
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None


def _create_mixed_audio_source(music_url: str, tts_file: str, music_volume: float = 0.2) -> Optional[discord.AudioSource]:
    try:
        result = MixedAudioSource(music_url, tts_file, music_volume)
        return result
    except Exception as e:
        logger.error(f"Error creating mixed audio source: {e}")
        return None


def _reduce_music_volume_for_tts(guild_id: int) -> Optional[float]:
    if guild_id not in music_bot.voice_clients:
        return None
    
    voice_client = music_bot.voice_clients[guild_id]
    if not voice_client.is_connected() or not voice_client.is_playing():
        return None
    
    if not voice_client.source or not isinstance(voice_client.source, discord.PCMVolumeTransformer):
        return None
    
    original_volume = voice_client.source.volume
    music_bot.original_volumes[guild_id] = original_volume
    voice_client.source.volume = 0.2
    
    return original_volume


def _restore_music_volume(guild_id: int, original_volume: Optional[float]) -> None:
    if guild_id in music_bot.original_volumes:
        volume_to_restore = music_bot.original_volumes.pop(guild_id)
    elif original_volume is not None:
        volume_to_restore = original_volume
    else:
        return
    
    if guild_id not in music_bot.voice_clients:
        return
    
    voice_client = music_bot.voice_clients[guild_id]
    if not voice_client.is_connected():
        return
    
    if voice_client.source and isinstance(voice_client.source, discord.PCMVolumeTransformer):
        voice_client.source.volume = volume_to_restore


async def leave_music(guild_id: int) -> Dict[str, Any]:
    if guild_id not in music_bot.voice_clients:
        return {'success': False, 'error': 'Bot not in voice channel'}

    await music_bot.voice_clients[guild_id].disconnect()
    del music_bot.voice_clients[guild_id]
    music_bot.queues.pop(guild_id, None)
    music_bot.current_songs.pop(guild_id, None)
    music_bot.original_volumes.pop(guild_id, None)

    if guild_id in music_bot.voice_sinks:
        music_bot.voice_sinks[guild_id].cleanup()
        del music_bot.voice_sinks[guild_id]

    return {'success': True, 'message': 'Left voice channel'}


async def speak_tts(guild_id: int, channel_id: int, text: str) -> Dict[str, Any]:
    provider = os.getenv('TTS_PROVIDER', 'elevenlabs')
    
    if provider == 'piper':
        return await speak_piper_tts(guild_id, channel_id, text)
    
    api_key = os.getenv("ELEVEN_API_KEY")
    if tts_generate is None or not api_key:
        return {'success': False, 'error': 'TTS unavailable: missing dependency or ELEVEN_API_KEY'}

    if set_eleven_api_key:
        set_eleven_api_key(api_key)

    resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id)
    if error:
        return {'success': False, 'error': error}
    
    voice_client = await music_bot.join_voice_channel(guild_id, resolved_channel_id)
    if not voice_client:
        return {'success': False, 'error': 'Failed to join voice channel'}

    music_source_info = music_bot.get_current_music_source(guild_id)
    was_playing = music_source_info is not None
    original_volume = None
    use_mixing = False

    if was_playing:
        original_volume = _reduce_music_volume_for_tts(guild_id)
        if original_volume is not None and music_source_info and music_source_info.get('url'):
            use_mixing = True

    try:
        audio_bytes = await asyncio.to_thread(
            tts_generate,
            text=text,
            voice=ELEVEN_VOICE_ID,
            model=ELEVEN_MODEL,
            output_format=ELEVEN_OUTPUT_FORMAT,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_fp:
            tmp_fp.write(audio_bytes)
            tmp_path = tmp_fp.name

        loop = music_bot.main_loop or asyncio.get_running_loop()

        async def cleanup_tts():
            await asyncio.sleep(ELEVEN_CLEANUP_DELAY)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            if was_playing:
                _restore_music_volume(guild_id, original_volume)

        def after_play(error):
            loop.call_soon_threadsafe(asyncio.create_task, cleanup_tts())

        if use_mixing and music_source_info:
            current_song = music_bot.current_songs.get(guild_id)
            if current_song:
                try:
                    loop = asyncio.get_running_loop()
                    song_url = current_song.get('url') or current_song.get('webpage_url', '')
                    if song_url:
                        fresh_song_data = await loop.run_in_executor(None, lambda: ytdl.extract_info(song_url, download=False))
                        if fresh_song_data:
                            if 'entries' in fresh_song_data and fresh_song_data['entries']:
                                fresh_song_data = fresh_song_data['entries'][0]
                            if fresh_song_data.get('url'):
                                music_url = fresh_song_data['url']
                            else:
                                music_url = music_source_info['url']
                        else:
                            music_url = music_source_info['url']
                    else:
                        music_url = music_source_info['url']
                except Exception as e:
                    logger.warning(f"Failed to get fresh streaming URL for mixing, using existing: {e}")
                    music_url = music_source_info['url']
            else:
                music_url = music_source_info['url']
            
            mixed_source = _create_mixed_audio_source(
                music_url,
                tmp_path,
                music_volume=0.5
            )
            if mixed_source:
                def mixed_after_play(error):
                    if mixed_source:
                        mixed_source.cleanup()
                    after_play(error)
                    if was_playing and current_song:
                        async def resume_music():
                            try:
                                player = await YTDLSource.from_url(current_song.get('url'), stream=True)
                                loop = music_bot.main_loop or asyncio.get_running_loop()
                                voice_client.play(
                                    player,
                                    after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, music_bot.play_next(guild_id)),
                                )
                            except Exception as e:
                                logger.error(f"Failed to resume music after TTS: {e}")
                        loop = music_bot.main_loop or asyncio.get_running_loop()
                        loop.call_soon_threadsafe(asyncio.create_task, resume_music())
                
                voice_client.stop()
                
                await asyncio.sleep(0.3)
                
                try:
                    logger.info(f"Playing mixed source (music + TTS) for guild {guild_id}, music_url: {music_url[:80]}...")
                    voice_client.play(mixed_source, after=mixed_after_play)
                    logger.info(f"Mixed source playback started, is_playing: {voice_client.is_playing()}")
                    return {'success': True, 'message': 'Speaking with music...'}
                except Exception as e:
                    logger.error(f"Failed to play mixed source: {e}")
                    if mixed_source:
                        mixed_source.cleanup()
                    raise
            logger.warning("Failed to create mixed audio source, falling back to pause/resume")

        if was_playing:
            voice_client.pause()
        
        player = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(tmp_path, options='-vn'), volume=1.0)
        voice_client.play(player, after=after_play)
        return {'success': True, 'message': 'Speaking...'}
    except Exception as e:
        logger.error(f"Error playing TTS: {e}")
        if was_playing:
            _restore_music_volume(guild_id, original_volume)
            if voice_client.is_paused():
                voice_client.resume()
        return {'success': False, 'error': f'Failed to play TTS: {str(e)}'}


async def speak_piper_tts(guild_id: int, channel_id: int, text: str) -> Dict[str, Any]:
    if 'piper' not in tts_providers or not tts_providers['piper']:
        return {'success': False, 'error': 'Piper TTS not configured'}

    resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id)
    if error:
        return {'success': False, 'error': error}
    
    voice_client = await music_bot.join_voice_channel(guild_id, resolved_channel_id)
    if not voice_client:
        return {'success': False, 'error': 'Failed to join voice channel'}

    music_source_info = music_bot.get_current_music_source(guild_id)
    was_playing = music_source_info is not None
    original_volume = None
    use_mixing = False

    if was_playing:
        original_volume = _reduce_music_volume_for_tts(guild_id)
        if original_volume is not None and music_source_info and music_source_info.get('url'):
            use_mixing = True

    try:
        piper_tts = tts_providers['piper']
        audio_path = await asyncio.to_thread(piper_tts.generate_speech, text)

        loop = music_bot.main_loop or asyncio.get_running_loop()

        async def cleanup_tts():
            await asyncio.sleep(PIPER_CLEANUP_DELAY)
            try:
                os.remove(audio_path)
            except OSError:
                pass
            if was_playing:
                _restore_music_volume(guild_id, original_volume)

        def after_play(error):
            loop.call_soon_threadsafe(asyncio.create_task, cleanup_tts())

        if use_mixing and music_source_info:
            current_song = music_bot.current_songs.get(guild_id)
            if current_song:
                try:
                    loop = asyncio.get_running_loop()
                    fresh_song_data = await loop.run_in_executor(None, lambda: ytdl.extract_info(current_song.get('url') or current_song.get('webpage_url', ''), download=False))
                    if fresh_song_data:
                        if 'entries' in fresh_song_data and fresh_song_data['entries']:
                            fresh_song_data = fresh_song_data['entries'][0]
                        if fresh_song_data.get('url'):
                            music_url = fresh_song_data['url']
                        else:
                            music_url = music_source_info['url']
                    else:
                        music_url = music_source_info['url']
                except Exception as e:
                    logger.warning(f"Failed to get fresh streaming URL for mixing, using existing: {e}")
                    music_url = music_source_info['url']
            else:
                music_url = music_source_info['url']
            
            mixed_source = _create_mixed_audio_source(
                music_url,
                audio_path,
                music_volume=0.2
            )
            if mixed_source:
                def mixed_after_play(error):
                    if mixed_source:
                        mixed_source.cleanup()
                    after_play(error)
                    if was_playing and current_song:
                        async def resume_music():
                            try:
                                player = await YTDLSource.from_url(current_song.get('url'), stream=True)
                                loop = music_bot.main_loop or asyncio.get_running_loop()
                                voice_client.play(
                                    player,
                                    after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, music_bot.play_next(guild_id)),
                                )
                            except Exception as e:
                                logger.error(f"Failed to resume music after TTS: {e}")
                        loop = music_bot.main_loop or asyncio.get_running_loop()
                        loop.call_soon_threadsafe(asyncio.create_task, resume_music())
                
                voice_client.stop()
                await asyncio.sleep(0.3)
                voice_client.play(mixed_source, after=mixed_after_play)
                return {'success': True, 'message': 'Speaking with Piper and music...'}
            logger.warning("Failed to create mixed audio source, falling back to pause/resume")

        if was_playing:
            voice_client.pause()
        
        player = discord.FFmpegPCMAudio(audio_path, options='-vn')
        voice_client.play(player, after=after_play)
        return {'success': True, 'message': 'Speaking with Piper...'}
    except Exception as e:
        logger.error(f"Piper TTS error: {e}")
        if was_playing:
            _restore_music_volume(guild_id, original_volume)
            if voice_client.is_paused():
                voice_client.resume()
        return {'success': False, 'error': str(e)}


@bot.event
async def on_ready():
    global bot_loop, chatbot
    bot_loop = asyncio.get_running_loop()
    music_bot.main_loop = bot_loop
    logger.info(f'Bot connected as {bot.user}')
    
    if chatbot and ZhipuChatbot:
        try:
            chatbot.bot = bot
            chatbot.music_bot = music_bot
            logger.info("ZhipuAI GLM chatbot configured with bot instances")
        except Exception as e:
            logger.warning(f"Failed to configure chatbot with bot instances: {e}")


def should_respond_with_chatbot(message) -> bool:
    content = message.content.lower().strip()

    if message.author.bot:
        return False

    checks = [
        'tangerina' in content,
        bool(bot.user) and bot.user.mentioned_in(message),
        message.guild is None,
    ]

    return any(checks)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    try:
        message_data = extract_message_data(message)
        should_chat = bool(chatbot) and should_respond_with_chatbot(message)

        if should_chat and chatbot:
            guild_id = message.guild.id if message.guild else None
            channel_id = message.channel.id
            user_id = message.author.id
            
            app_functions = {
                "get_user_voice_channel": get_user_voice_channel,
                "play_music": play_music,
                "play_spotify_music": play_spotify_music,
                "stop_music": stop_music,
                "skip_music": skip_music,
                "pause_music": pause_music,
                "resume_music": resume_music,
                "set_volume": set_volume,
                "get_queue": get_queue,
                "leave_music": leave_music,
                "speak_tts": speak_tts,
            }
            
            context = []
            async def generate_response():
                return await chatbot.generate_response_with_tools(
                    message.content,
                    context=context,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    app_functions=app_functions
                )
            
            typing_ctx = message.channel.typing() if hasattr(message.channel, 'typing') else None
            if typing_ctx:
                async with typing_ctx:
                    response, tool_calls = await generate_response()
            else:
                response, tool_calls = await generate_response()
            
            if response and response.strip():
                await message.channel.send(response)
            
            message_data['chatbot_response'] = response
            message_data['tool_calls'] = tool_calls
            
            if N8N_WEBHOOK_URL:
                await forward_to_n8n(message_data)
        elif N8N_WEBHOOK_URL:
            typing_ctx = message.channel.typing() if hasattr(message.channel, 'typing') else None
            if typing_ctx:
                async with typing_ctx:
                    await forward_to_n8n(message_data)
            else:
                await forward_to_n8n(message_data)

    except Exception as e:
        logger.error(f'Error processing message: {e}')


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f'Discord event error in {event}: {args}, {kwargs}')


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

    success = run_async(leave_music(guild_id))
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

    result = run_async(get_user_voice_channel(guild_id, user_id))
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

    result = run_async(play_music(guild_id, channel_id, query), timeout=30)
    return jsonify(result), 200 if result.get('success') else 500


@flask_app.route('/music/stop', methods=['POST'])
@require_bot_ready
def music_stop():
    data = request.get_json() or {}
    guild_id = parse_guild_id(data)
    if guild_id is None:
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(stop_music(guild_id))
    return jsonify(result), 200 if result.get('success') else 404


@flask_app.route('/music/skip', methods=['POST'])
@require_bot_ready
def music_skip():
    data = request.get_json() or {}
    guild_id = parse_guild_id(data)
    if guild_id is None:
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(skip_music(guild_id))
    return jsonify(result), 200 if result.get('success') else 404


@flask_app.route('/music/pause', methods=['POST'])
@require_bot_ready
def music_pause():
    data = request.get_json() or {}
    guild_id = parse_guild_id(data)
    if guild_id is None:
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(pause_music(guild_id))
    return jsonify(result), 200 if result.get('success') else 404


@flask_app.route('/music/resume', methods=['POST'])
@require_bot_ready
def music_resume():
    data = request.get_json() or {}
    guild_id = parse_guild_id(data)
    if guild_id is None:
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(resume_music(guild_id))
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

    result = run_async(set_volume(guild_id, volume))
    return jsonify(result), 200 if result.get('success') else 404


@flask_app.route('/music/queue', methods=['GET'])
@require_bot_ready
def music_queue():
    try:
        guild_id = int(request.args.get('guild_id'))
    except (ValueError, TypeError):
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(get_queue(guild_id))
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

    result = run_async(play_spotify_music(guild_id, channel_id, spotify_uri), timeout=60)
    return jsonify(result), 200 if result.get('success') else 500


@flask_app.route('/music/leave', methods=['POST'])
@require_bot_ready
def music_leave():
    data = request.get_json() or {}
    guild_id = parse_guild_id(data)
    if guild_id is None:
        return jsonify({'error': 'guild_id must be an integer'}), 400

    result = run_async(leave_music(guild_id))
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

    result = run_async(speak_tts(guild_id, channel_id, text), timeout=30)
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

    result = run_async(speak_piper_tts(guild_id, channel_id, text), timeout=30)
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


def run_flask():
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


def run_discord():
    try:
        logger.info('Starting Discord bot...')
        bot.run(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Fatal error: {e}')


if not ZHIPU_API_KEY:
    logger.warning("ZHIPU_API_KEY not set. Chatbot will be disabled.")
if not tts_providers:
    logger.warning("No TTS provider configured. Voice responses disabled.")


if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info('Flask API started on http://0.0.0.0:5000')
    run_discord()