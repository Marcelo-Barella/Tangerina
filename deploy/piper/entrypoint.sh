#!/bin/bash
set -e

MODEL_PATH="/app/models/pt_BR-faber-medium.onnx"
MODEL_JSON_PATH="/app/models/pt_BR-faber-medium.onnx.json"
MODEL_DIR="/app/models"

# Create models directory if it doesn't exist
mkdir -p "$MODEL_DIR"

# Download model files if they don't exist
if [ ! -f "$MODEL_PATH" ]; then
    echo "Model file not found. Downloading pt_BR-faber-medium model..."
    cd "$MODEL_DIR"
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx" -O "$MODEL_PATH" || {
        echo "ERROR: Failed to download model file" >&2
        exit 1
    }
    echo "Model file downloaded successfully"
fi

if [ ! -f "$MODEL_JSON_PATH" ]; then
    echo "Model JSON file not found. Downloading pt_BR-faber-medium.json..."
    cd "$MODEL_DIR"
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json" -O "$MODEL_JSON_PATH" || {
        echo "WARNING: Failed to download model JSON file (optional)" >&2
    }
    echo "Model JSON file downloaded successfully"
fi

# Verify model file exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "ERROR: Model file still not found at $MODEL_PATH" >&2
    exit 1
fi

echo "Model file verified: $MODEL_PATH"
echo "Starting Piper TTS server..."

# Execute the main command
exec "$@"

