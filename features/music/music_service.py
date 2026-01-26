import re
import logging
import discord
from typing import Optional, Dict, Any, Tuple
from features.music.music_bot import MusicBot, YTDLSource, FFMPEG_OPTIONS

logger = logging.getLogger(__name__)


async def _resolve_voice_channel(guild_id: int, channel_id: int, bot, music_bot: MusicBot) -> Tuple[Optional[int], Optional[str]]:
    guild = bot.get_guild(guild_id)
    if not guild:
        return None, f'Guild {guild_id} not found'
    
    channel = guild.get_channel(channel_id)
    if not channel:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception:
            pass
    
    if channel and not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        current_vc = music_bot._get_current_voice_channel(guild_id)
        if current_vc and current_vc.channel:
            channel_id = current_vc.channel.id
            logger.info(f'Using bot\'s current voice channel {channel_id} instead of text channel {channel.id}')
        else:
            return None, f'Channel {channel_id} is a text channel. Please specify a voice channel or use EnterChannel first.'
    
    return channel_id, None


class MusicService:
    def __init__(self, bot, music_bot: MusicBot, spotify_client=None):
        self.bot = bot
        self.music_bot = music_bot
        self.spotify_client = spotify_client

    async def get_user_voice_channel(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
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

    async def play_spotify_music(self, guild_id: int, channel_id: int, spotify_uri: str) -> Dict[str, Any]:
        if not self.spotify_client:
            return {'success': False, 'error': 'Spotify integration not configured'}

        parsed = self.spotify_client.parse_uri(spotify_uri)
        if not parsed:
            return {'success': False, 'error': 'Invalid Spotify URI'}

        uri_type = parsed['type']
        tracks = []

        if uri_type == 'track':
            track_info = self.spotify_client.get_track_info(spotify_uri)
            if track_info:
                tracks = [track_info]
        elif uri_type == 'playlist':
            tracks = self.spotify_client.get_playlist_tracks(spotify_uri)
        elif uri_type == 'album':
            tracks = self.spotify_client.get_album_tracks(spotify_uri)
        else:
            return {'success': False, 'error': f'Unsupported type: {uri_type}'}

        if not tracks:
            return {'success': False, 'error': 'No tracks found'}

        resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id, self.bot, self.music_bot)
        if error:
            return {'success': False, 'error': error}
        
        voice_client = await self.music_bot.join_voice_channel(guild_id, resolved_channel_id)
        if not voice_client:
            return {'success': False, 'error': 'Failed to join voice channel'}

        if guild_id not in self.music_bot.queues:
            self.music_bot.queues[guild_id] = []

        for track in tracks:
            self.music_bot.queues[guild_id].append({
                'source': 'spotify',
                'spotify_track': track,
                'title': track.get('name', 'Unknown'),
                'artists': [artist.get('name', '') for artist in track.get('artists', [])]
            })

        if not voice_client.is_playing():
            await self.music_bot.play_next(guild_id, self.spotify_client)
            current = self.music_bot.current_songs.get(guild_id)
            return {
                'success': True,
                'tracks_queued': len(tracks),
                'message': f"Now playing: {current.get('title', 'Unknown') if current else 'Unknown'}"
            }

        return {'success': True, 'tracks_queued': len(tracks), 'message': f"Added {len(tracks)} track(s) to queue"}

    async def play_music(self, guild_id: int, channel_id: int, query: str) -> Dict[str, Any]:
        if self.spotify_client:
            spotify_patterns = [r'spotify:(track|playlist|album|artist):', r'open\.spotify\.com/(track|playlist|album|artist)/']
            if any(re.search(pattern, query) for pattern in spotify_patterns):
                return await self.play_spotify_music(guild_id, channel_id, query)

        resolved_channel_id, error = await _resolve_voice_channel(guild_id, channel_id, self.bot, self.music_bot)
        if error:
            return {'success': False, 'error': error}
        
        voice_client = await self.music_bot.join_voice_channel(guild_id, resolved_channel_id)
        if not voice_client:
            return {'success': False, 'error': 'Failed to join voice channel'}

        song_data = await YTDLSource.search_youtube(query, ytdl=self.music_bot.ytdl)
        if not song_data:
            return {'success': False, 'error': f'No results found for: {query}'}

        if guild_id not in self.music_bot.queues:
            self.music_bot.queues[guild_id] = []

        if voice_client.is_playing():
            self.music_bot.queues[guild_id].append(song_data)
            return {'success': True, 'song': song_data, 'queued': True, 'message': f"Added '{song_data['title']}' to queue"}

        player = await YTDLSource.from_url(song_data['url'], stream=True, ytdl=self.music_bot.ytdl, ffmpeg_options=FFMPEG_OPTIONS)
        import asyncio
        loop = self.music_bot.main_loop or asyncio.get_running_loop()
        voice_client.play(
            player,
            after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, self.music_bot.play_next(guild_id, self.spotify_client)),
        )
        self.music_bot.current_songs[guild_id] = song_data
        return {'success': True, 'song': song_data, 'queued': False, 'message': f"Now playing: {song_data['title']}"}

    async def stop_music(self, guild_id: int) -> Dict[str, Any]:
        if guild_id not in self.music_bot.voice_clients:
            return {'success': False, 'error': 'Bot not in voice channel'}

        self.music_bot.voice_clients[guild_id].stop()
        self.music_bot.queues[guild_id] = []
        return {'success': True, 'message': 'Music stopped and queue cleared'}

    async def skip_music(self, guild_id: int) -> Dict[str, Any]:
        if guild_id in self.music_bot.voice_clients and self.music_bot.voice_clients[guild_id].is_playing():
            self.music_bot.voice_clients[guild_id].stop()
            return {'success': True, 'message': 'Skipped current song'}
        return {'success': False, 'error': 'No music playing'}

    async def pause_music(self, guild_id: int) -> Dict[str, Any]:
        if guild_id in self.music_bot.voice_clients and self.music_bot.voice_clients[guild_id].is_playing():
            self.music_bot.voice_clients[guild_id].pause()
            return {'success': True, 'message': 'Music paused'}
        return {'success': False, 'error': 'No music playing'}

    async def resume_music(self, guild_id: int) -> Dict[str, Any]:
        if guild_id in self.music_bot.voice_clients and self.music_bot.voice_clients[guild_id].is_paused():
            self.music_bot.voice_clients[guild_id].resume()
            return {'success': True, 'message': 'Music resumed'}
        return {'success': False, 'error': 'Music not paused'}

    async def set_volume(self, guild_id: int, volume: int) -> Dict[str, Any]:
        if guild_id not in self.music_bot.voice_clients:
            return {'success': False, 'error': 'Bot not in voice channel'}

        vc = self.music_bot.voice_clients[guild_id]
        if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = volume / 100
            return {'success': True, 'volume': volume, 'message': f'Volume set to {volume}%'}
        return {'success': False, 'error': 'Cannot adjust volume'}

    async def get_queue(self, guild_id: int, limit: Optional[int] = None, 
                       info_level: str = "all", offset: int = 0, 
                       include_current: bool = True) -> Dict[str, Any]:
        queue = self.music_bot.queues.get(guild_id, [])
        current = self.music_bot.current_songs.get(guild_id)
        total = len(queue)
        
        if limit == 0:
            filtered_queue = []
        else:
            start_idx = offset
            end_idx = start_idx + limit if limit else len(queue)
            filtered_queue = queue[start_idx:end_idx]
        
        def extract_fields(item: Dict[str, Any], position: Optional[int] = None) -> Dict[str, Any]:
            if info_level == "minimal":
                result = {"title": item.get("title", "Unknown")}
                if position is not None:
                    result["position"] = position
                return result
            elif info_level == "name":
                return {"title": item.get("title", "Unknown")}
            elif info_level == "link":
                result = {"title": item.get("title", "Unknown")}
                url = item.get("url") or item.get("webpage_url")
                if url:
                    result["url"] = url
                return result
            else:
                result = {"title": item.get("title", "Unknown")}
                url = item.get("url") or item.get("webpage_url")
                if url:
                    result["url"] = url
                if "duration" in item:
                    result["duration"] = item["duration"]
                if "artists" in item:
                    result["artists"] = item["artists"]
                return result
        
        processed_queue = []
        for idx, item in enumerate(filtered_queue):
            processed_queue.append(extract_fields(item, offset + idx))
        
        processed_current = None
        if include_current and current:
            processed_current = extract_fields(current)
        
        return {
            'queue': processed_queue,
            'current': processed_current,
            'total': total,
            'returned': len(processed_queue)
        }

    async def leave_music(self, guild_id: int) -> Dict[str, Any]:
        if guild_id not in self.music_bot.voice_clients:
            return {'success': False, 'error': 'Bot not in voice channel'}

        await self.music_bot.voice_clients[guild_id].disconnect()
        del self.music_bot.voice_clients[guild_id]
        self.music_bot.queues.pop(guild_id, None)
        self.music_bot.current_songs.pop(guild_id, None)
        self.music_bot.original_volumes.pop(guild_id, None)

        if guild_id in self.music_bot.voice_sinks:
            self.music_bot.voice_sinks[guild_id].cleanup()
            del self.music_bot.voice_sinks[guild_id]

        return {'success': True, 'message': 'Left voice channel'}
