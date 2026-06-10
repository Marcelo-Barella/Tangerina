#!/bin/bash
set -e

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "OmniVoice sidecar starting"
echo "  OMNIVOICE_PRECISION=${OMNIVOICE_PRECISION:-int8}"
echo "  OMNIVOICE_DEVICE=${OMNIVOICE_DEVICE:-auto}"
echo "  OMNIVOICE_LOAD_ASR=${OMNIVOICE_LOAD_ASR:-false}"

exec "$@"
