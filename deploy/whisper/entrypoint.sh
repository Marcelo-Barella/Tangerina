#!/bin/sh
set -e
echo "Starting Whisper ASR sidecar..."

use_api=0
if [ -n "${OPENAI_API_KEY}" ]; then
  case "${WHISPER_USE_OPENAI_API}" in
    1|true|yes) use_api=1 ;;
    0|false|no) use_api=0 ;;
    *)
      if [ -z "${OPENAI_BASE_URL}" ]; then
        use_api=1
      fi
      ;;
  esac
fi

if [ "$use_api" -eq 1 ]; then
  echo "Provider: OpenAI Whisper API (whisper-1)"
else
  echo "Provider: local (${WHISPER_LOCAL_ENGINE:-faster-whisper})"
  echo "WHISPER_MODEL=${WHISPER_MODEL:-base}"
  echo "WHISPER_DEVICE=${WHISPER_DEVICE:-cpu}"
  echo "WHISPER_COMPUTE_TYPE=${WHISPER_COMPUTE_TYPE:-int8}"
fi
echo "WHISPER_LANGUAGE=${WHISPER_LANGUAGE:-pt}"
echo "XDG_CACHE_HOME=${XDG_CACHE_HOME:-/app/.cache}"
echo "WHISPER_PORT=${WHISPER_PORT:-5002}"
mkdir -p "${XDG_CACHE_HOME:-/app/.cache}"
exec "$@"
