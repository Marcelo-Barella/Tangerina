## Whisper ASR sidecar

HTTP transcription service used when `WHISPER_PROVIDER=sidecar`. Prefers the **OpenAI Whisper API** (`whisper-1`) when `OPENAI_API_KEY` is set; otherwise falls back to local `openai-whisper`.

### Defaults

- **Provider**: OpenAI API when `OPENAI_API_KEY` is set, else local `openai-whisper`
- **Language**: `pt`
- **Port**: `5002`
- **Local model cache**: `deploy/whisper/cache` (local fallback only)

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

Set `OPENAI_API_KEY` in the repo root `.env` (loaded via `env_file`).

### Healthcheck

```bash
curl -sS http://localhost:5002/health
```

### Transcribe (multipart/form-data)

```bash
curl -sS \
  -F "file=@./your_audio.wav" \
  http://localhost:5002/transcribe
```

### Bot without sidecar

If `OPENAI_API_KEY` is set and `WHISPER_PROVIDER` is empty, the bot uses `openai-api` directly (no sidecar container required).

### Configuration

```bash
WHISPER_LANGUAGE=pt docker compose up --build -d
```

For local fallback only:

```bash
WHISPER_MODEL=base WHISPER_LANGUAGE=pt docker compose up --build -d
```
