# Voice smoke (Discord-free TTS + STT)

Use this harness to verify Piper, Whisper, and optional OmniVoice sidecars (and the bot Flask preview routes) without joining a Discord voice channel.

## Prerequisites

- Network access to the host running Tangerina (remote server or local Docker).
- Sidecars healthy on ports **5001** (Piper), **5002** (Whisper), and optionally **5003** (OmniVoice).
- Bot API on **5000** only if you test `/tts/preview` and `/stt/transcribe`.

## Sidecar roundtrip script

From the repo root:

```bash
chmod +x scripts/smoke_voice_roundtrip.sh

# Local Docker (default URLs http://127.0.0.1:5001–5003)
./scripts/smoke_voice_roundtrip.sh

# Remote host (replace with your Tailscale or LAN address)
BASE_URL=http://<host> ./scripts/smoke_voice_roundtrip.sh

# Include OmniVoice TTS in the same STT check
RUN_OMNIVOICE=1 BASE_URL=http://<host> ./scripts/smoke_voice_roundtrip.sh

# Also exercise bot Flask routes (no guild/channel)
USE_BOT=1 BASE_URL=http://<host> ./scripts/smoke_voice_roundtrip.sh
```

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `BASE_URL` | `http://127.0.0.1` | Host prefix; sidecars use `:5001`, `:5002`, `:5003`, bot `:5000` |
| `PIPER_URL` / `WHISPER_URL` / `OMNIVOICE_URL` / `BOT_URL` | derived from `BASE_URL` | Override individual services |
| `SMOKE_PHRASE` | `Olá, este é um teste de voz do Tangerina.` | Expected transcript (accent/case normalized); passed to TTS JSON as `{"text":...}` |
| `RUN_OMNIVOICE` | `0` | Set to `1` to run OmniVoice TTS roundtrip |
| `USE_BOT` | `0` | Set to `1` to hit `/tts/preview` and `/stt/transcribe` on the bot |

Exit code **0** = PASS, **1** = FAIL.

## Bot preview routes (no Discord)

These routes do not require the bot to be in a voice channel or `bot_ready`.

**TTS preview** — `POST /tts/preview`

```bash
curl -sS -X POST "http://<host>:5000/tts/preview" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Olá, este é um teste de voz do Tangerina.","provider":"piper"}' \
  -o /tmp/preview.wav
```

Optional `provider`: `piper` (default) or `omnivoice` when configured.

**STT** — `POST /stt/transcribe` (multipart `file`)

```bash
curl -sS -X POST "http://<host>:5000/stt/transcribe" \
  -F "file=@/tmp/preview.wav;type=audio/wav"
```

Response: `{"text":"..."}` proxied from the Whisper sidecar (`WHISPER_API_URL`).

Discord speak routes (`/tts/speak`, `/tts/piper/speak`, etc.) are unchanged and still require guild/channel context.
