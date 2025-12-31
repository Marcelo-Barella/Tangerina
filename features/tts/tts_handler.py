import os
import asyncio
import tempfile
import logging
from typing import Optional, Dict, Any
import discord

logger = logging.getLogger(__name__)

ELEVEN_CLEANUP_DELAY = 20
PIPER_CLEANUP_DELAY = 5
MIXED_AUDIO_DELAY = 0.3
MUSIC_VOLUME_REDUCED = 0.2
ELEVEN_MIXED_VOLUME = 0.5
PIPER_MIXED_VOLUME = 0.2


class MixedAudioSource(discord.AudioSource):
    FRAME_SIZE = 3840
    
    def __init__(self, music_url: str, tts_file: str, music_volume: float = 0.2):
        import subprocess
        import time
        
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
            import subprocess
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


async def _get_fresh_music_url(guild_id: int, current_song: dict, fallback_url: str, ytdl) -> str:
    try:
        loop = asyncio.get_running_loop()
        song_url = current_song.get('url') or current_song.get('webpage_url', '')
        if song_url:
            fresh_song_data = await loop.run_in_executor(None, lambda: ytdl.extract_info(song_url, download=False))
            if fresh_song_data:
                if 'entries' in fresh_song_data and fresh_song_data['entries']:
                    fresh_song_data = fresh_song_data['entries'][0]
                if fresh_song_data.get('url'):
                    return fresh_song_data['url']
    except Exception as e:
        logger.warning(f"Failed to get fresh streaming URL for mixing, using existing: {e}")
    return fallback_url


def _reduce_music_volume_for_tts(guild_id: int, music_bot) -> Optional[float]:
    if guild_id not in music_bot.voice_clients:
        return None
    
    voice_client = music_bot.voice_clients[guild_id]
    if not voice_client.is_connected() or not voice_client.is_playing():
        return None
    
    if not voice_client.source or not isinstance(voice_client.source, discord.PCMVolumeTransformer):
        return None
    
    original_volume = voice_client.source.volume
    music_bot.original_volumes[guild_id] = original_volume
    voice_client.source.volume = MUSIC_VOLUME_REDUCED
    
    return original_volume


def _restore_music_volume(guild_id: int, original_volume: Optional[float], music_bot) -> None:
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


async def _resume_music_after_tts(guild_id: int, current_song: dict, voice_client, music_bot, YTDLSource):
    try:
        player = await YTDLSource.from_url(current_song.get('url'), stream=True)
        loop = music_bot.main_loop or asyncio.get_running_loop()
        voice_client.play(
            player,
            after=lambda e: loop.call_soon_threadsafe(asyncio.create_task, music_bot.play_next(guild_id)),
        )
    except Exception as e:
        logger.error(f"Failed to resume music after TTS: {e}")


async def _play_tts_with_mixing(
    guild_id: int,
    voice_client,
    music_source_info: Dict[str, Any],
    tts_file: str,
    current_song: Optional[dict],
    music_bot,
    ytdl,
    YTDLSource,
    music_volume: float,
    cleanup_delay: float,
    cleanup_callback
):
    music_url = await _get_fresh_music_url(guild_id, current_song, music_source_info['url'], ytdl) if current_song else music_source_info['url']
    
    mixed_source = MixedAudioSource(music_url, tts_file, music_volume=music_volume)
    if mixed_source:
        def mixed_after_play(error):
            if mixed_source:
                mixed_source.cleanup()
            cleanup_callback()
            if current_song:
                loop = music_bot.main_loop or asyncio.get_running_loop()
                loop.call_soon_threadsafe(asyncio.create_task, _resume_music_after_tts(guild_id, current_song, voice_client, music_bot, YTDLSource))
        
        voice_client.stop()
        await asyncio.sleep(MIXED_AUDIO_DELAY)
        
        try:
            logger.info(f"Playing mixed source (music + TTS) for guild {guild_id}, music_url: {music_url[:80]}...")
            voice_client.play(mixed_source, after=mixed_after_play)
            logger.info(f"Mixed source playback started, is_playing: {voice_client.is_playing()}")
            return True
        except Exception as e:
            logger.error(f"Failed to play mixed source: {e}")
            if mixed_source:
                mixed_source.cleanup()
            raise
    return False


async def speak_tts_unified(
    guild_id: int,
    channel_id: int,
    text: str,
    tts_provider: str,
    tts_providers: dict,
    tts_generate,
    set_eleven_api_key,
    ELEVEN_API_KEY,
    ELEVEN_VOICE_ID,
    ELEVEN_MODEL,
    ELEVEN_OUTPUT_FORMAT,
    music_bot,
    _resolve_voice_channel,
    ytdl,
    YTDLSource
) -> Dict[str, Any]:
    if tts_provider == 'piper':
        if 'piper' not in tts_providers or not tts_providers['piper']:
            return {'success': False, 'error': 'Piper TTS not configured'}
        
        piper_tts = tts_providers['piper']
        audio_path = await asyncio.to_thread(piper_tts.generate_speech, text)
        cleanup_delay = PIPER_CLEANUP_DELAY
        mixed_volume = PIPER_MIXED_VOLUME
        audio_file = audio_path
        use_ffmpeg_direct = True
    else:
        if tts_generate is None or not ELEVEN_API_KEY:
            return {'success': False, 'error': 'TTS unavailable: missing dependency or ELEVEN_API_KEY'}
        
        if set_eleven_api_key:
            set_eleven_api_key(ELEVEN_API_KEY)
        
        audio_bytes = await asyncio.to_thread(
            tts_generate,
            text=text,
            voice=ELEVEN_VOICE_ID,
            model=ELEVEN_MODEL,
            output_format=ELEVEN_OUTPUT_FORMAT,
        )
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_fp:
            tmp_fp.write(audio_bytes)
            audio_file = tmp_fp.name
        
        cleanup_delay = ELEVEN_CLEANUP_DELAY
        mixed_volume = ELEVEN_MIXED_VOLUME
        use_ffmpeg_direct = False

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
        original_volume = _reduce_music_volume_for_tts(guild_id, music_bot)
        if original_volume is not None and music_source_info and music_source_info.get('url'):
            use_mixing = True

    try:
        loop = music_bot.main_loop or asyncio.get_running_loop()

        async def cleanup_tts():
            await asyncio.sleep(cleanup_delay)
            try:
                os.remove(audio_file)
            except OSError:
                pass
            if was_playing:
                _restore_music_volume(guild_id, original_volume, music_bot)

        def after_play(error):
            loop.call_soon_threadsafe(asyncio.create_task, cleanup_tts())

        if use_mixing and music_source_info:
            current_song = music_bot.current_songs.get(guild_id)
            try:
                success = await _play_tts_with_mixing(
                    guild_id,
                    voice_client,
                    music_source_info,
                    audio_file,
                    current_song,
                    music_bot,
                    ytdl,
                    YTDLSource,
                    mixed_volume,
                    cleanup_delay,
                    after_play
                )
                if success:
                    provider_name = 'Piper' if tts_provider == 'piper' else 'ElevenLabs'
                    return {'success': True, 'message': f'Speaking with {provider_name} and music...'}
            except Exception as e:
                logger.warning(f"Failed to create mixed audio source, falling back to pause/resume: {e}")

        if was_playing:
            voice_client.pause()
        
        if use_ffmpeg_direct:
            player = discord.FFmpegPCMAudio(audio_file, options='-vn')
        else:
            player = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_file, options='-vn'), volume=1.0)
        
        voice_client.play(player, after=after_play)
        provider_name = 'Piper' if tts_provider == 'piper' else 'ElevenLabs'
        return {'success': True, 'message': f'Speaking with {provider_name}...'}
    except Exception as e:
        logger.error(f"Error playing TTS: {e}")
        if was_playing:
            _restore_music_volume(guild_id, original_volume, music_bot)
            if voice_client.is_paused():
                voice_client.resume()
        return {'success': False, 'error': f'Failed to play TTS: {str(e)}'}
