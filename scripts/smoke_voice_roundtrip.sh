#!/usr/bin/env bash
set -euo pipefail

DEFAULT_SMOKE_PHRASE='Olá, este é um teste de voz do Tangerina.'
SMOKE_PHRASE="${SMOKE_PHRASE:-$DEFAULT_SMOKE_PHRASE}"

BASE_URL="${BASE_URL:-http://127.0.0.1}"
BASE_URL="${BASE_URL%/}"
PIPER_URL="${PIPER_URL:-${BASE_URL}:5001}"
WHISPER_URL="${WHISPER_URL:-${BASE_URL}:5002}"
OMNIVOICE_URL="${OMNIVOICE_URL:-${BASE_URL}:5003}"
BOT_URL="${BOT_URL:-${BASE_URL}:5000}"

RUN_OMNIVOICE="${RUN_OMNIVOICE:-0}"
USE_BOT="${USE_BOT:-0}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

json_tts_text() {
  python3 -c 'import json, sys; print(json.dumps({"text": sys.argv[1]}))' "$SMOKE_PHRASE"
}

json_bot_preview() {
  python3 -c 'import json, sys; print(json.dumps({"text": sys.argv[1], "provider": sys.argv[2]}))' "$SMOKE_PHRASE" "${1:-piper}"
}

normalize_text() {
  python3 -c '
import re
import sys
import unicodedata

text = sys.argv[1].lower()
text = unicodedata.normalize("NFD", text)
text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
print(" ".join(text.split()))
' "$1"
}

parse_transcript_json() {
  python3 -c 'import json, sys; print(json.load(sys.stdin).get("text", "").strip())'
}

fuzzy_match() {
  local expected="$1"
  local actual="$2"
  local norm_expected norm_actual
  norm_expected="$(normalize_text "$expected")"
  norm_actual="$(normalize_text "$actual")"
  if [[ -z "$norm_actual" ]]; then
    return 1
  fi
  if [[ "$norm_actual" == *"$norm_expected"* ]] || [[ "$norm_expected" == *"$norm_actual"* ]]; then
    return 0
  fi
  local key
  for key in $norm_expected; do
    if [[ ${#key} -lt 4 ]]; then
      continue
    fi
    if [[ "$norm_actual" != *"$key"* ]]; then
      return 1
    fi
  done
  return 0
}

run_sidecar_roundtrip() {
  local label="$1"
  local tts_url="$2"
  local wav_path="$TMP_DIR/${label}.wav"
  local tts_body
  tts_body="$(json_tts_text)"

  echo "==> [$label] TTS POST ${tts_url}/tts"
  if ! curl -fsS -X POST "${tts_url}/tts" \
    -H 'Content-Type: application/json' \
    -d "$tts_body" \
    -o "$wav_path"; then
    echo "FAIL: [$label] TTS request failed (check ${tts_url}/tts)" >&2
    return 1
  fi

  if [[ ! -s "$wav_path" ]]; then
    echo "FAIL: [$label] empty WAV from TTS" >&2
    return 1
  fi

  echo "==> [$label] STT POST ${WHISPER_URL}/transcribe"
  local transcript
  transcript="$(curl -fsS -X POST "${WHISPER_URL}/transcribe" \
    -F "file=@${wav_path};type=audio/wav" | parse_transcript_json)"

  echo "[$label] phrase:  ${SMOKE_PHRASE}"
  echo "[$label] transcript: ${transcript}"

  if fuzzy_match "$SMOKE_PHRASE" "$transcript"; then
    echo "PASS: [$label] sidecar TTS+STT roundtrip"
    return 0
  fi
  echo "FAIL: [$label] transcript did not match expected phrase" >&2
  return 1
}

run_bot_roundtrip() {
  local wav_path="$TMP_DIR/bot-preview.wav"
  local preview_body
  preview_body="$(json_bot_preview piper)"

  echo "==> [bot] TTS POST ${BOT_URL}/tts/preview"
  if ! curl -fsS -X POST "${BOT_URL}/tts/preview" \
    -H 'Content-Type: application/json' \
    -d "$preview_body" \
    -o "$wav_path"; then
    echo "FAIL: [bot] /tts/preview request failed" >&2
    return 1
  fi

  if [[ ! -s "$wav_path" ]]; then
    echo "FAIL: [bot] empty WAV from /tts/preview" >&2
    return 1
  fi

  echo "==> [bot] STT POST ${BOT_URL}/stt/transcribe"
  local transcript
  transcript="$(curl -fsS -X POST "${BOT_URL}/stt/transcribe" \
    -F "file=@${wav_path};type=audio/wav" | parse_transcript_json)"

  echo "[bot] phrase:  ${SMOKE_PHRASE}"
  echo "[bot] transcript: ${transcript}"

  if fuzzy_match "$SMOKE_PHRASE" "$transcript"; then
    echo "PASS: [bot] Flask preview TTS+STT roundtrip"
    return 0
  fi
  echo "FAIL: [bot] transcript did not match expected phrase" >&2
  return 1
}

status=0
if ! run_sidecar_roundtrip piper "$PIPER_URL"; then
  status=1
fi

if [[ "$RUN_OMNIVOICE" == "1" ]]; then
  if ! run_sidecar_roundtrip omnivoice "$OMNIVOICE_URL"; then
    status=1
  fi
fi

if [[ "$USE_BOT" == "1" ]]; then
  if ! run_bot_roundtrip; then
    status=1
  fi
fi

if [[ "$status" -eq 0 ]]; then
  echo "Voice smoke: PASS"
else
  echo "Voice smoke: FAIL" >&2
fi
exit "$status"
