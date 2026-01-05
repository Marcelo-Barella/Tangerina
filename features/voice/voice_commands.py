import os
import asyncio
import tempfile
import logging
import re
import io
import wave
import struct
from typing import Dict, Optional, Callable, Any, Set, List
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
AUDIO_BUFFER_MAXLEN = 150
AUDIO_SAMPLE_RATE = 48000
AUDIO_SAMPLE_WIDTH = 2
AUDIO_CHANNELS = 1
TRANSCRIPTION_TIMEOUT = 30
LISTENING_VOLUME = 20

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

    def __init__(
        self,
        bot_instance: Any,
        voice_client: Any,
        guild_id: int,
        zhipu_api_key: Optional[str],
        whisper_provider: str,
        music_service: Any,
        chatbot: Optional[Any] = None,
        tts_providers: Optional[Dict[str, Any]] = None,
        speak_tts_func: Optional[Callable] = None,
        openai_api_key: Optional[str] = None
    ):
        if voice_recv:
            super().__init__()
        self.bot = bot_instance
        self._voice_client = voice_client
        self.guild_id = guild_id
        self.audio_buffers: Dict[int, deque] = {}
        self.speaking_users: Set[int] = set()
        self.zhipu_api_key = zhipu_api_key
        self.whisper_provider = whisper_provider
        self.whisper_model: Optional[Any] = None
        self.whisper_api_url = os.getenv('WHISPER_API_URL', 'http://whisper-asr:5002')
        self.openai_api_key = openai_api_key
        self.music_service = music_service
        self.chatbot = chatbot
        self.tts_providers = tts_providers or {}
        self.speak_tts_func = speak_tts_func
        self.listening_mode: Dict[int, bool] = {}
        self.listening_tasks: Dict[int, asyncio.Task] = {}
        self.original_volumes: Dict[int, float] = {}
        self._validate_provider_config()

    def _validate_provider_config(self) -> None:
        if not self.zhipu_api_key and self.whisper_provider == 'zhipu':
            logger.warning("ZHIPU_API_KEY not set. GLM-ASR-2512 voice transcription unavailable.")
        if self.whisper_provider == 'openai' and whisper is None:
            logger.warning("openai-whisper package not installed. Whisper transcription unavailable.")
        if self.whisper_provider == 'openai-api' and not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not set. OpenAI Whisper API transcription unavailable.")
        if self.whisper_provider == 'openai-api' and self.openai_api_key:
            logger.info("OpenAI Whisper API provider enabled (whisper-1)")
        if self.whisper_provider == 'sidecar':
            logger.info(f"Whisper sidecar provider enabled, API URL: {self.whisper_api_url}")

    def wants_opus(self) -> bool:
        return False

    def write(self, user: Optional[discord.Member], data: Any) -> None:
        if user is None:
            return
        if user.id not in self.audio_buffers:
            self.audio_buffers[user.id] = deque(maxlen=AUDIO_BUFFER_MAXLEN)
        if hasattr(data, 'pcm') and data.pcm:
            self.audio_buffers[user.id].append(data.pcm)

    if voice_recv:
        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_start(self, member: discord.Member) -> None:
            self.speaking_users.add(member.id)

        @voice_recv.AudioSink.listener()
        def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
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

    async def process_speech(self, member: discord.Member) -> None:
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
            await self._route_speech(member, text.strip())
        except Exception as e:
            logger.error(f"Error processing speech from {member.display_name}: {e}")

    async def _route_speech(self, member: discord.Member, text: str) -> None:
        text_lower = text.lower().strip()
        is_listening = self.listening_mode.get(member.id, False)
        
        if WAKE_WORD in text_lower:
            wake_word_index = text_lower.find(WAKE_WORD)
            command_text = text[wake_word_index + len(WAKE_WORD):].strip()
            command_text = re.sub(r'^[,.\s]+', '', command_text)
            
            if command_text and not is_listening:
                await self._handle_voice_command(member, command_text)
            elif not is_listening:
                await self._activate_listening_mode(member)
            elif is_listening:
                await self._handle_listening_mode(member, text.strip())
        elif is_listening:
            await self._handle_listening_mode(member, text.strip())
        else:
            await self._handle_voice_command(member, text.strip())

    def _combine_audio_chunks(self, chunks: List[bytes]) -> io.BytesIO:
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
            wav_file.setnchannels(AUDIO_CHANNELS)
            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
            wav_file.setframerate(AUDIO_SAMPLE_RATE)
            wav_file.writeframes(mono_audio)
        wav_buffer.seek(0)
        return wav_buffer

    def _load_whisper_model(self) -> Optional[Any]:
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

    async def _transcribe_audio(self, audio_data: io.BytesIO) -> Optional[str]:
        provider_map: Dict[str, Callable[[io.BytesIO], Any]] = {
            'openai-api': self._transcribe_openai_api,
            'openai': self._transcribe_openai_local,
            'sidecar': self._transcribe_sidecar,
            'zhipu': self._transcribe_zhipu,
        }
        handler = provider_map.get(self.whisper_provider)
        if handler:
            return await handler(audio_data)
        return await self._transcribe_zhipu(audio_data)

    async def _transcribe_openai_api(self, audio_data: io.BytesIO) -> Optional[str]:
        if not self.openai_api_key:
            logger.error("OPENAI_API_KEY not set for OpenAI Whisper API")
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)
            audio_data.seek(0)
            audio_bytes = audio_data.read()
            tmp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_file_path = tmp_file.name
                with open(tmp_file_path, 'rb') as audio_file:
                    result = await asyncio.to_thread(
                        client.audio.transcriptions.create,
                        model="whisper-1",
                        file=audio_file,
                        language="pt",
                        prompt="Você é tangerina, uma assistente virtual de música brasileiro. Você executa comandos como 'toca', 'para', 'pula', 'pausa', 'continua', 'fila', 'sai', 'volume', etc. Todos relacionados a música."
                    )
                text = result.text.strip() if hasattr(result, 'text') else ''
                return text if text else None
            finally:
                self._cleanup_temp_file(tmp_file_path)
        except Exception as e:
            logger.error(f"OpenAI Whisper API transcription error: {e}")
            return None

    async def _transcribe_openai_local(self, audio_data: io.BytesIO) -> Optional[str]:
        if whisper is None:
            logger.error("openai-whisper package not installed")
            return None
        model = self._load_whisper_model()
        if model is None:
            return None
        audio_data.seek(0)
        tmp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_file.write(audio_data.read())
                tmp_file_path = tmp_file.name
            result = await asyncio.to_thread(model.transcribe, tmp_file_path, language="pt")
            text = result.get('text', '').strip()
            return text if text else None
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None
        finally:
            self._cleanup_temp_file(tmp_file_path)

    async def _transcribe_sidecar(self, audio_data: io.BytesIO) -> Optional[str]:
        audio_data.seek(0)
        audio_bytes = audio_data.read()
        url = f"{self.whisper_api_url.rstrip('/')}/transcribe"
        data = aiohttp.FormData()
        data.add_field('file', audio_bytes, filename='audio.wav', content_type='audio/wav')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=TRANSCRIPTION_TIMEOUT)) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get('text', '').strip()
                        return text if text else None
                    error_text = await response.text()
                    logger.error(f"Whisper sidecar transcription error: HTTP {response.status} - {error_text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("Whisper sidecar transcription timeout")
            return None
        except Exception as e:
            logger.error(f"Whisper sidecar transcription error: {e}")
            return None

    async def _transcribe_zhipu(self, audio_data: io.BytesIO) -> Optional[str]:
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
                async with session.post(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=TRANSCRIPTION_TIMEOUT)) as response:
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

    def _cleanup_temp_file(self, file_path: Optional[str]) -> None:
        if file_path:
            try:
                os.unlink(file_path)
            except Exception:
                pass

    def _get_text_channel(self) -> Optional[discord.TextChannel]:
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return None
        return next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)

    async def _handle_voice_command(self, member: discord.Member, text: str) -> None:
        text_channel = self._get_text_channel()
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

    async def _handle_play(self, channel: discord.TextChannel, text: str) -> None:
        query = re.sub(r'\b(toca|play|tocar)\b', '', text).strip()
        if not query:
            return
        try:
            result = await self.music_service.play_music(self.guild_id, channel.id, query)
            await channel.send(result.get('message', 'Comando executado'))
        except Exception as e:
            logger.error(f"Error executing play command: {e}")
            await channel.send("Erro ao tocar música")

    async def _handle_stop(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.stop_music(self.guild_id)
        await channel.send(result.get('message', 'Música parada'))

    async def _handle_skip(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.skip_music(self.guild_id)
        await channel.send(result.get('message', 'Música pulada'))

    async def _handle_pause(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.pause_music(self.guild_id)
        await channel.send(result.get('message', 'Música pausada'))

    async def _handle_resume(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.resume_music(self.guild_id)
        await channel.send(result.get('message', 'Música retomada'))

    async def _handle_queue(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.get_queue(self.guild_id)
        queue = result.get('queue', [])
        if not queue:
            await channel.send("Fila vazia")
            return
        queue_text = "\n".join([f"{i+1}. {song.get('title', 'Unknown')}" for i, song in enumerate(queue[:QUEUE_DISPLAY_LIMIT])])
        await channel.send(f"Fila:\n```{queue_text}```")

    async def _handle_leave(self, channel: discord.TextChannel, _: str) -> None:
        result = await self.music_service.leave_music(self.guild_id)
        await channel.send(result.get('message', 'Saindo do canal'))

    async def _handle_volume(self, channel: discord.TextChannel, text: str) -> None:
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

    async def _cancel_listening_task(self, member_id: int) -> None:
        if member_id not in self.listening_tasks:
            return
        task = self.listening_tasks.pop(member_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _activate_listening_mode(self, member: discord.Member) -> None:
        current_volume = await self._get_current_volume()
        if current_volume is None:
            logger.warning(f"Cannot activate listening mode for {member.display_name}: no music source available (volume cannot be adjusted)")
            return
        self.original_volumes[member.id] = current_volume
        self.listening_mode[member.id] = True
        await self.music_service.set_volume(self.guild_id, LISTENING_VOLUME)
        logger.info(f"Activated listening mode for {member.display_name}, volume lowered to {LISTENING_VOLUME}")
        await self._cancel_listening_task(member.id)
        async def listening_timeout():
            await asyncio.sleep(LISTENING_DURATION)
            if self.listening_mode.get(member.id, False):
                await self._deactivate_listening_mode(member)
        self.listening_tasks[member.id] = asyncio.create_task(listening_timeout())

    async def _deactivate_listening_mode(self, member: discord.Member) -> None:
        if not self.listening_mode.get(member.id, False):
            return
        self.listening_mode[member.id] = False
        await self._cancel_listening_task(member.id)
        original_volume = self.original_volumes.pop(member.id, None)
        if original_volume is not None:
            await self.music_service.set_volume(self.guild_id, int(original_volume))
            logger.info(f"Deactivated listening mode for {member.display_name}, volume restored to {int(original_volume)}")

    async def _handle_listening_mode(self, member: discord.Member, text: str) -> None:
        text_lower = text.lower().strip()
        if any(keyword in text_lower for keyword in CANCEL_KEYWORDS):
            await self._deactivate_listening_mode(member)
            return
        await self._cancel_listening_task(member.id)
        await self._deactivate_listening_mode(member)
        if not self.chatbot:
            return
        try:
            response = await self._generate_chatbot_response(member, text)
            if not response:
                return
            text_channel = self._get_text_channel()
            if not text_channel:
                return
            await text_channel.send(response)
            await self._speak_response_if_enabled(response)
        except Exception as e:
            logger.error(f"Chatbot error in listening mode: {e}")

    async def _generate_chatbot_response(self, member: discord.Member, text: str) -> Optional[str]:
        if not self.chatbot.memory_manager:
            return await self.chatbot.generate_response(text)
        retrieved_memories = await self.chatbot.memory_manager.retrieve_context(
            text, self.guild_id, None, member.id
        )
        response = await self.chatbot.generate_response_with_tools(
            text, [], self.guild_id, None, member.id, {}, retrieved_memories
        )
        if isinstance(response, tuple):
            response, tool_calls = response
        else:
            tool_calls = []
        await self.chatbot.memory_manager.store_conversation(
            text, response, self.guild_id, None, member.id, tool_calls
        )
        return response

    async def _speak_response_if_enabled(self, response: str) -> None:
        if 'piper' not in self.tts_providers or not self.tts_providers['piper'] or not self.speak_tts_func:
            return
        voice_client = self.music_service.music_bot.voice_clients.get(self.guild_id)
        if voice_client and voice_client.is_connected():
            await self.speak_tts_func(self.guild_id, voice_client.channel.id, response)

    def cleanup(self) -> None:
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
