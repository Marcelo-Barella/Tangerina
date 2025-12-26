import asyncio
import logging
from typing import Optional, Dict, Any
import discord
import yt_dlp

logger = logging.getLogger(__name__)

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


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, ytdl=None, ffmpeg_options=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        logger.info(f"Creating audio source for: {data.get('title', 'Unknown')}")

        try:
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except discord.errors.ClientException as e:
            if "ffmpeg" in str(e).lower():
                raise Exception("FFmpeg não está instalado. Instale o FFmpeg para usar a funcionalidade de música.")
            raise

    @classmethod
    async def search_youtube(cls, query: str, ytdl=None) -> Optional[Dict[str, Any]]:
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
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.queues: Dict[int, list] = {}
        self.current_songs: Dict[int, dict] = {}
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        self.voice_sinks: Dict[int, Any] = {}
        self.original_volumes: Dict[int, float] = {}
        self.ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

    def _check_nacl(self):
        try:
            import nacl
        except ImportError:
            raise RuntimeError("PyNaCl library needed for voice. Install with: pip install PyNaCl")

    def _get_existing_voice_client(self, guild_id: int, channel_id: int) -> Optional[discord.VoiceClient]:
        for vc in self.bot.voice_clients:
            if vc.guild.id == guild_id and vc.is_connected():
                if vc.channel and vc.channel.id == channel_id:
                    if guild_id not in self.voice_clients:
                        self.voice_clients[guild_id] = vc
                    return vc
        return None

    def _get_current_voice_channel(self, guild_id: int) -> Optional[discord.VoiceClient]:
        for vc in self.bot.voice_clients:
            if vc.guild.id == guild_id and vc.is_connected() and vc.channel:
                if guild_id not in self.voice_clients:
                    self.voice_clients[guild_id] = vc
                return vc
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_connected() and vc.channel:
                return vc
        return None

    async def _move_or_connect(self, guild_id: int, channel, voice_recv_module=None) -> Optional[discord.VoiceClient]:
        if guild_id in self.voice_clients:
            vc = self.voice_clients[guild_id]
            if vc.is_connected():
                if vc.channel and vc.channel.id != channel.id:
                    await vc.move_to(channel)
                return vc
            del self.voice_clients[guild_id]

        if voice_recv_module:
            vc = await channel.connect(cls=voice_recv_module.VoiceRecvClient)
            self.voice_clients[guild_id] = vc
            if guild_id not in self.voice_sinks:
                from voice_commands import VoiceCommandSink
                sink = VoiceCommandSink(
                    self.bot, vc, guild_id,
                    getattr(self, 'zhipu_api_key', ''),
                    getattr(self, 'whisper_provider', 'zhipu'),
                    getattr(self, 'music_service', None),
                    getattr(self, 'chatbot', None),
                    getattr(self, 'tts_providers', {}),
                    getattr(self, 'speak_tts_func', None)
                )
                sink.music_bot_ref = self
                if hasattr(vc, 'listen'):
                    vc.listen(sink)
                self.voice_sinks[guild_id] = sink
            else:
                sink = self.voice_sinks[guild_id]
                sink._voice_client = vc
                if hasattr(vc, 'listen'):
                    vc.listen(sink)
        else:
            vc = await channel.connect()
            self.voice_clients[guild_id] = vc

        return vc

    async def join_voice_channel(self, guild_id: int, channel_id: int, voice_recv_module=None) -> Optional[discord.VoiceClient]:
        if voice_recv_module is None:
            try:
                from discord.ext import voice_recv as vr_module
                voice_recv_module = vr_module
            except ImportError:
                voice_recv_module = None
        self._check_nacl()

        if not self.bot.is_ready():
            logger.warning("Bot not ready, waiting for gateway connection...")
            await asyncio.sleep(1)
            if not self.bot.is_ready():
                logger.error("Bot still not ready after wait")
                return None

        guild = self.bot.get_guild(guild_id)
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
        
        if channel and not hasattr(channel, 'connect'):
            logger.error(f'Channel {channel_id} is not a voice channel or cannot be connected to')
            return None

        existing = self._get_existing_voice_client(guild_id, channel_id)
        if existing:
            return existing

        try:
            result = await self._move_or_connect(guild_id, channel, voice_recv_module)
            return result
        except (discord.errors.ClientException, Exception) as e:
            if 'already connected' in str(e).lower():
                return self._get_existing_voice_client(guild_id, channel_id)
            if 'pynacl' in str(e).lower() or 'nacl' in str(e).lower():
                raise RuntimeError("PyNaCl library needed for voice. Install with: pip install PyNaCl") from e
            if 'closing transport' in str(e).lower() or 'connection reset' in str(e).lower():
                logger.warning(f'Gateway connection issue during voice connect, will retry: {e}')
                await asyncio.sleep(1)
                try:
                    result = await self._move_or_connect(guild_id, channel, voice_recv_module)
                    return result
                except Exception as retry_e:
                    logger.error(f'Voice connection retry failed: {retry_e}')
                    return None
            raise
        except Exception as e:
            logger.error(f'Error joining voice channel: {e}')
            return None

    async def play_next(self, guild_id: int, spotify_client=None):
        if guild_id not in self.queues or not self.queues[guild_id]:
            return
        if guild_id not in self.voice_clients:
            return

        voice_client = self.voice_clients[guild_id]
        next_song = self.queues[guild_id].pop(0)

        try:
            if next_song.get('source') == 'spotify' and spotify_client:
                next_song = await self._resolve_spotify_track(next_song, spotify_client)
                if not next_song:
                    await self.play_next(guild_id, spotify_client)
                    return

            player = await YTDLSource.from_url(next_song['url'], stream=True, ytdl=self.ytdl, ffmpeg_options=FFMPEG_OPTIONS)
            loop = self.main_loop or asyncio.get_running_loop()
            voice_client.play(
                player,
                after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, self.play_next(guild_id, spotify_client)),
            )
            self.current_songs[guild_id] = next_song
        except Exception as e:
            logger.error(f"Error playing next song: {e}")
            await self.play_next(guild_id, spotify_client)

    async def _resolve_spotify_track(self, song_data: dict, spotify_client) -> Optional[dict]:
        spotify_track = song_data.get('spotify_track')
        if not spotify_track or not spotify_client:
            return None

        youtube_query = spotify_client.track_to_youtube_query(spotify_track)
        if not youtube_query:
            return None

        return await YTDLSource.search_youtube(youtube_query, ytdl=self.ytdl)

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
