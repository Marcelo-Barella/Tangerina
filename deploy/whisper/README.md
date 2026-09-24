## Whisper ASR sidecar

HTTP transcription service used when `WHISPER_PROVIDER=sidecar`. Local default is **faster-whisper**; **openai-whisper** is opt-in via `WHISPER_LOCAL_ENGINE`. Cloud Whisper API is used only when `OPENAI_API_KEY` is set **and** `OPENAI_BASE_URL` is empty (unless `WHISPER_USE_OPENAI_API` forces the choice).

### Defaults

- **Cloud**: OpenAI Whisper API when `OPENAI_API_KEY` is set and there is no `OPENAI_BASE_URL` (override with `WHISPER_USE_OPENAI_API`)
- **Local engine**: `faster-whisper` (`WHISPER_LOCAL_ENGINE=faster-whisper`); set `openai-whisper` for the stock PyTorch package
- **Model**: `WHISPER_MODEL=base` (same env as the bot in-process provider)
- **Language**: `pt`
- **Device / compute**: `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`
- **Port**: `5002`
- **Local model cache**: `deploy/whisper/cache`
- **Config source**: root `../../.env` via `env_file` (compose does not override Whisper/OpenAI keys with empty host substitutions)

### Prerequisite: docker network

This compose file attaches to the external network `tangerina-network` (same as `deploy/piper/docker-compose.yml`).

If you don't have it yet:

```bash
docker network create tangerina-network
```

### Run

From `deploy/whisper/`:

```bash
docker compose up --build -d
```

Set `OPENAI_API_KEY` in the repo root `.env` (loaded via `env_file`) to force the cloud path inside the sidecar.

Local faster-whisper (no API key):

```bash
WHISPER_LOCAL_ENGINE=faster-whisper WHISPER_MODEL=base WHISPER_LANGUAGE=pt docker compose up --build -d
```

Local openai-whisper fallback:

```bash
WHISPER_LOCAL_ENGINE=openai-whisper WHISPER_MODEL=base WHISPER_LANGUAGE=pt docker compose up --build -d
```

### Healthcheck

```bash
curl -sS http://localhost:5002/health
```

Warm the local model:

```bash
curl -sS 'http://localhost:5002/ready?warm=1'
```

### Transcribe (multipart/form-data)

```bash
curl -sS \
  -F "file=@./your_audio.wav" \
  http://localhost:5002/transcribe
```

### Local voice stack (wake + faster-whisper + local LLM)

Point the bot at an OpenAI-compatible local server (Ollama example) and keep STT on this sidecar:

```bash
MODEL_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3.2
WHISPER_PROVIDER=sidecar
WHISPER_LOCAL_ENGINE=faster-whisper
TTS_PROVIDER=piper
PIPER_API_URL=http://piper-tts:5001
```

When `OPENAI_BASE_URL` is set (shared `.env` with the bot), the sidecar keeps STT on the local engine even if `OPENAI_API_KEY` is a dummy local value such as `ollama`. Force cloud Whisper inside the sidecar with `WHISPER_USE_OPENAI_API=1`, or force local with `WHISPER_USE_OPENAI_API=0`.

### Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `WHISPER_LOCAL_ENGINE` | `faster-whisper` | `faster-whisper` or `openai-whisper` |
| `WHISPER_MODEL` | `base` | Model size for local engines |
| `WHISPER_LANGUAGE` | `pt` | Forced language |
| `WHISPER_DEVICE` | `cpu` | faster-whisper device |
| `WHISPER_COMPUTE_TYPE` | `int8` | faster-whisper compute type |
| `WHISPER_USE_OPENAI_API` | auto | `1`/`0` force; else API only if key set and no `OPENAI_BASE_URL` |
| `OPENAI_BASE_URL` | empty | When set, sidecar stays on local STT (local LLM stacks) |
