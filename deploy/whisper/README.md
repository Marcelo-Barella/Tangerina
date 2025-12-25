## Whisper ASR sidecar (OpenAI Whisper, pt)

This service runs **OpenAI Whisper locally** as a small HTTP API, similar to the existing Piper TTS sidecar.

### Defaults

- **Model**: `base`
- **Language**: `pt`
- **Port**: `5002`
- **Model cache**: `deploy/whisper/cache` (persisted via volume mount)

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

### Configuration

Set env vars when starting compose:

```bash
WHISPER_MODEL=base WHISPER_LANGUAGE=pt docker compose up --build -d
```

### Notes

- The first transcription triggers Whisper to **download model weights** into the cache directory. Subsequent runs reuse the cached weights.


