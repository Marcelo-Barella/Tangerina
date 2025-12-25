#!/bin/bash
set -e

echo "Starting Whisper ASR sidecar..."
echo "WHISPER_MODEL=${WHISPER_MODEL:-medium}"
echo "WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-pt}"
echo "XDG_CACHE_HOME=${XDG_CACHE_HOME:-/app/.cache}"
echo "WHISPER_PORT=${WHISPER_PORT:-5002}"

# Ensure cache dir exists (model weights will download on first load)
mkdir -p "${XDG_CACHE_HOME:-/app/.cache}"

exec "$@"


