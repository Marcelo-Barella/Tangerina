# OmniVoice TTS Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OmniVoice as a third TTS provider via a Docker sidecar with INT8 default for 6 GB VRAM, voice design mode, and bot HTTP client integration.

**Architecture:** Flask sidecar (`deploy/omnivoice/`) loads `k2-fsa/OmniVoice` with `load_asr=False`, applies TorchAO INT8 quantization by default, exposes `POST /tts`. Bot uses `OmnivoiceTTS` HTTP client and `speak_tts_unified` omnivoice branch.

**Tech Stack:** Python 3.11, Flask, omnivoice, PyTorch, torchao, Docker, requests

**Spec:** `docs/superpowers/specs/2026-06-10-omnivoice-tts-design.md`

---

## File map

| File | Role |
|------|------|
| `deploy/omnivoice/server.py` | Flask API, warmup, generation |
| `deploy/omnivoice/model_loader.py` | Device/precision detection, model load |
| `deploy/omnivoice/quantize.py` | INT8/INT4 TorchAO quantization |
| `deploy/omnivoice/Dockerfile` | CUDA PyTorch + omnivoice image |
| `features/tts/omnivoice_tts.py` | Bot HTTP client |
| `features/tts/tts_handler.py` | Playback dispatch |
| `app.py` | Provider registration |
| `flask_routes.py` | `POST /tts/omnivoice/speak` |

---

## Tasks (completed in this branch)

- [x] Sidecar: Dockerfile, server, model_loader, quantize, entrypoint, compose
- [x] Bot: OmnivoiceTTS client, tts_handler branch, app.py wiring
- [x] API: `/tts/omnivoice/speak` route
- [x] Deploy: `deploy/docker-compose.yaml` omnivoice-tts service
- [x] Docs: README, `.env.example`
- [x] Tests: unit `test_omnivoice_tts.py`, integration route validation

## Verification

```bash
pytest tests/unit/test_omnivoice_tts.py tests/integration/test_flask_routes.py -v
cd deploy/omnivoice && docker compose up --build -d
curl -f http://localhost:5003/health
```
