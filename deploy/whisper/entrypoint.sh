#!/bin/sh
set -e
echo "Starting Whisper ASR sidecar..."
if [ -n "${OPENAI_API_KEY}" ]; then
  echo "Provider: OpenAI Whisper API (whisper-1)"
else
  echo "Provider: local openai-whisper (OPENAI_API_KEY not set)"
  echo "WHISPER_MODEL=${WHISPER_MODEL:-base}"
fi
echo "WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-pt}"
echo "XDG_CACHE_HOME=${XDG_CACHE_HOME:-/app/.cache}"
echo "WHISPER_PORT=${WHISPER_PORT:-5002}"
mkdir -p "${XDG_CACHE_HOME:-/app/.cache}"
exec "$@"
