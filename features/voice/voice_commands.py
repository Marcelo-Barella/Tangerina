import os
import asyncio
import tempfile
import logging
import re
import io
import wave
import struct
from typing import Dict, Optional
from collections import deque
import aiohttp
import discord

logger = logging.getLogger(__name__)

MIN_AUDIO_CHUNKS = 10
QUEUE_DISPLAY_LIMIT = 5
VOLUME_MIN = 0
VOLUME_MAX = 100
WAKE_WORD = 'tangerina'
LISTENING_DURATION = 5.0
CANCEL_KEYWORDS = ['cancel', 'cancelar', 'stop', 'parar', 'nevermind', 'esquece']

try:
    from discord.ext import voice_recv
    BaseSink = voice_recv.AudioSink
except ImportError:
    voice_recv = None
    BaseSink = object

try:
    import whisper
except ImportError:
    whisper = None

class VoiceCommandSink(BaseSink):
    VOICE_COMMANDS = {
        'play': ['toca', 'play', 'tocar'],
        'stop': ['para', 'stop', 'parar'],
        'skip': ['pula', 'skip', 'pular'],
        'pause': ['pausa', 'pause', 'pausar'],
        'resume': ['continua', 'resume', 'continuar'],
        'queue': ['fila', 'queue', 'fila de música'],
        'leave': ['sai', 'leave', 'sair'],
    }

    def __init__(self, bot_instance, voice_client, guild_id: int, zhipu_api_key: str, whisper_provider: str, music_service, chatbot=None, tts_providers=None, speak_tts_func=None):
        if voice_recv:
            super().__init__()
        self.bot = bot_instance
        self._voice_client = voice_client
        self.guild_id = guild_id
        self.audio_buffers: Dict[int, deque] = {}
        self.speaking_users = set()
        self.zhipu_api_key = zhipu_api_key
        self.whisper_provider = whisper_provider
        self.whisper_model = None
        self.music_service = music_service
        self.chatbot = chatbot
        self.tts_providers = tts_providers or {}
        self.speak_tts_func = speak_tts_func
        self.listening_mode: Dict[int, bool] = {}
        self.listening_tasks: Dict[int, asyncio.Task] = {}
        self.original_volumes: Dict[int, float] = {}

        if not zhipu_api_key and whisper_provider == 'zhipu':
            logger.warning("ZHIPU_API_KEY not set. GLM-ASR-2512 voice transcription unavailable.")
        if whisper_provider == 'openai' and whisper is None:
            logger.warning("openai-whisper package not installed. Whisper transcription unavailable.")

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data):
        if user is None:
            return

        if user.id not in self.audio_buffers:
            self.audio_buffers[user.id] = deque(maxlen=150)

        if hasattr(data, 'pcm') and data.pcm:
            self.audio_buffers[user.id].append(data.pcm)

    if voice_recv:
        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_start(self, member):
            self.speaking_users.add(member.id)

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_stop(self, member):
            if member.id not in self.speaking_users:
                return
            self.speaking_users.remove(member.id)
            if not hasattr(self, 'music_bot_ref'):
                return
            music_bot = self.music_bot_ref
            loop = music_bot.main_loop or getattr(self.bot, 'loop', None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.process_speech(member), loop)
            else:
                logger.error("No running event loop available to process speech")

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
            if not text or not text.strip():
                return
            logger.info(f"Transcribed from {member.display_name}: {text}")
            text_lower = text.lower().strip()
            is_listening = self.listening_mode.get(member.id, False)
            if WAKE_WORD in text_lower and not is_listening:
                await self._activate_listening_mode(member)
            elif is_listening:
                await self._handle_listening_mode(member, text.strip())
            else:
                await self._handle_voice_command(member, text.strip())
        except Exception as e:
            logger.error(f"Error processing speech from {member.display_name}: {e}")

    def _combine_audio_chunks(self, chunks):
        combined = b''.join(chunks)
        try:
            import audioop
            mono_audio = audioop.tomono(combined, 2, 1.0, 1.0)
        except (ImportError, AttributeError):
            stereo_samples = struct.unpack(f'<{len(combined)//2}h', combined)
            mono_samples = [(stereo_samples[i] + stereo_samples[i + 1]) // 2
                          for i in range(0, len(stereo_samples) - 1, 2)]
            mono_audio = struct.pack(f'<{len(mono_samples)}h', *mono_samples)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(mono_audio)
        wav_buffer.seek(0)
        return wav_buffer

    def _load_whisper_model(self):
        if self.whisper_model is not None:
            return self.whisper_model
        if whisper is None:
            logger.error("openai-whisper package not available")
            return None
        try:
            logger.info("Loading Whisper model (medium) for Portuguese transcription...")
            self.whisper_model = whisper.load_model("medium")
            logger.info("Whisper model loaded successfully")
            return self.whisper_model
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return None

    async def _transcribe_audio(self, audio_data):
        if self.whisper_provider == 'openai':
            if whisper is None:
                logger.error("openai-whisper package not installed")
                return None
            model = self._load_whisper_model()
            if model is None:
                return None
            audio_data.seek(0)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_file.write(audio_data.read())
                tmp_file_path = tmp_file.name
            try:
                result = await asyncio.to_thread(model.transcribe, tmp_file_path, language="pt")
                text = result.get('text', '').strip()
                return text if text else None
            except Exception as e:
                logger.error(f"Whisper transcription error: {e}")
                return None
            finally:
                try:
                    os.unlink(tmp_file_path)
                except Exception:
                    pass
        if not self.zhipu_api_key:
            return None
        audio_data.seek(0)
        audio_bytes = audio_data.read()
        url = "https://api.z.ai/api/paas/v4/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.zhipu_api_key}"}
        data = aiohttp.FormData()
        data.add_field('model', 'glm-asr-2512')
        data.add_field('stream', 'false')
        data.add_field('file', audio_bytes, filename='audio.wav', content_type='audio/wav')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('text', '')
                        return text if text else None
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
        text_channel = next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
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
        }
        for cmd, keywords in self.VOICE_COMMANDS.items():
            if any(word in text_lower for word in keywords):
                await command_handlers[cmd](text_channel, text_lower)
                return
        if 'volume' in text_lower:
            await self._handle_volume(text_channel, text_lower)

    async def _handle_play(self, channel, text):
        query = re.sub(r'\b(toca|play|tocar)\b', '', text).strip()
        if not query:
            return
        try:
            result = await self.music_service.play_music(self.guild_id, channel.id, query)
            await channel.send(result.get('message', 'Comando executado'))
        except Exception as e:
            logger.error(f"Error executing play command: {e}")
            await channel.send("Erro ao tocar música")

    async def _handle_stop(self, channel, _):
        result = await self.music_service.stop_music(self.guild_id)
        await channel.send(result.get('message', 'Música parada'))

    async def _handle_skip(self, channel, _):
        result = await self.music_service.skip_music(self.guild_id)
        await channel.send(result.get('message', 'Música pulada'))

    async def _handle_pause(self, channel, _):
        result = await self.music_service.pause_music(self.guild_id)
        await channel.send(result.get('message', 'Música pausada'))

    async def _handle_resume(self, channel, _):
        result = await self.music_service.resume_music(self.guild_id)
        await channel.send(result.get('message', 'Música retomada'))

    async def _handle_queue(self, channel, _):
        result = await self.music_service.get_queue(self.guild_id)
        queue = result.get('queue', [])
        if not queue:
            await channel.send("Fila vazia")
            return
        queue_text = "\n".join([f"{i+1}. {song.get('title', 'Unknown')}" for i, song in enumerate(queue[:QUEUE_DISPLAY_LIMIT])])
        await channel.send(f"Fila:\n```{queue_text}```")

    async def _handle_leave(self, channel, _):
        result = await self.music_service.leave_music(self.guild_id)
        await channel.send(result.get('message', 'Saindo do canal'))

    async def _handle_volume(self, channel, text):
        volume_match = re.search(r'\d+', text)
        if not volume_match:
            return
        volume = int(volume_match.group())
        if not (VOLUME_MIN <= volume <= VOLUME_MAX):
            return
        result = await self.music_service.set_volume(self.guild_id, volume)
        await channel.send(result.get('message', f'Volume ajustado para {volume}%'))

    async def _get_current_volume(self) -> Optional[float]:
        vc = self.music_service.music_bot.voice_clients.get(self.guild_id)
        if not vc or not vc.source or not isinstance(vc.source, discord.PCMVolumeTransformer):
            return None
        return vc.source.volume * 100

    async def _activate_listening_mode(self, member):
        current_volume = await self._get_current_volume()
        if current_volume is None:
            logger.warning(f"Cannot activate listening mode for {member.display_name}: no music source available (volume cannot be adjusted)")
            return
        self.original_volumes[member.id] = current_volume
        self.listening_mode[member.id] = True
        await self.music_service.set_volume(self.guild_id, 20)
        logger.info(f"Activated listening mode for {member.display_name}, volume lowered to 20")
        async def listening_timeout():
            await asyncio.sleep(LISTENING_DURATION)
            if self.listening_mode.get(member.id, False):
                await self._deactivate_listening_mode(member)
        if member.id in self.listening_tasks:
            old_task = self.listening_tasks[member.id]
            if not old_task.done():
                old_task.cancel()
                try:
                    await old_task
                except asyncio.CancelledError:
                    pass
        self.listening_tasks[member.id] = asyncio.create_task(listening_timeout())

    async def _deactivate_listening_mode(self, member):
        if not self.listening_mode.get(member.id, False):
            return
        self.listening_mode[member.id] = False
        if member.id in self.listening_tasks:
            task = self.listening_tasks[member.id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.listening_tasks[member.id]
        original_volume = self.original_volumes.pop(member.id, None)
        if original_volume is not None:
            await self.music_service.set_volume(self.guild_id, int(original_volume))
            logger.info(f"Deactivated listening mode for {member.display_name}, volume restored to {int(original_volume)}")

    async def _handle_listening_mode(self, member, text: str):
        text_lower = text.lower().strip()
        if any(keyword in text_lower for keyword in CANCEL_KEYWORDS):
            await self._deactivate_listening_mode(member)
            return
        if member.id in self.listening_tasks:
            task = self.listening_tasks[member.id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.listening_tasks[member.id]
        await self._deactivate_listening_mode(member)
        if not self.chatbot:
            return
        try:
            response = await self.chatbot.generate_response(text)
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                return
            text_channel = next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
            if not text_channel:
                return
            await text_channel.send(response)
            if 'piper' in self.tts_providers and self.tts_providers['piper'] and self.speak_tts_func:
                voice_client = self.music_service.music_bot.voice_clients.get(self.guild_id)
                if voice_client and voice_client.is_connected():
                    await self.speak_tts_func(self.guild_id, voice_client.channel.id, response)
        except Exception as e:
            logger.error(f"Chatbot error in listening mode: {e}")

    def cleanup(self):
        self.audio_buffers.clear()
        self.speaking_users.clear()
        for task in list(self.listening_tasks.values()):
            if not task.done():
                try:
                    task.cancel()
                except Exception as e:
                    logger.warning(f"Error canceling task in cleanup: {e}")
        self.listening_tasks.clear()
        self.listening_mode.clear()
        self.original_volumes.clear()
