#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import re
from typing import Any, Dict, Tuple

from flask import Flask, Response, jsonify, request, send_file

app = Flask(__name__)

PIPER_BIN = os.getenv("PIPER_BIN", "/usr/local/bin/piper")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "/app/models/pt_BR-faber-medium.onnx")

def sanitize_text_for_piper(text: str) -> str:
    """Remove emojis and other problematic characters that cause piper to crash."""
    # Remove emojis (Unicode ranges for emojis)
    # This pattern matches most emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
        "\U00002600-\U000026FF"  # miscellaneous symbols
        "\U00002700-\U000027BF"  # dingbats
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    # Remove other problematic control characters but keep printable characters including Portuguese accented letters
    # Keep: letters (including accented), numbers, punctuation, whitespace
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

@app.route("/health", methods=["GET"])
def health() -> Tuple[Response, int]:
    return jsonify({"status": "ok"}), 200

@app.route("/tts", methods=["POST"])
def tts() -> Tuple[Response, int] | Response:
    data: Dict[str, Any] | None = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    if "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400
    
    text = data["text"]
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Text must be a non-empty string"}), 400
    
    original_text = text
    text = sanitize_text_for_piper(text)
    
    if not text.strip():
        return jsonify({"error": "Text contains only unsupported characters"}), 400
    
    if not os.path.exists(PIPER_MODEL_PATH):
        error_msg = f"Model file not found at {PIPER_MODEL_PATH}. Please ensure the model file is downloaded to the Docker volume."
        return jsonify({"error": error_msg}), 500
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        output_path = tmp_file.name
    
    try:
        cmd = [
            PIPER_BIN,
            "--model", PIPER_MODEL_PATH,
            "--output_file", output_path
        ]
        
        espeak_data = os.getenv("ESPEAK_DATA")
        if espeak_data:
            cmd.extend(["--espeak_data", espeak_data])
        
        process = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            timeout=30
        )
        
        if process.returncode != 0:
            error_msg = (process.stderr or "").strip() or "piper failed"
            return jsonify({"error": error_msg}), 500
        
        if not os.path.exists(output_path):
            return jsonify({"error": "Audio file not generated"}), 500
        
        return send_file(
            output_path,
            mimetype="audio/wav",
            as_attachment=True,
            download_name="output.wav"
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "TTS generation timed out"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

if __name__ == "__main__":
    if not os.path.exists(PIPER_BIN):
        print(f"Error: Piper binary not found at {PIPER_BIN}", file=sys.stderr)
        sys.exit(1)
    
    model_dir = os.path.dirname(PIPER_MODEL_PATH)
    if not os.path.exists(model_dir):
        print(f"Warning: Model directory does not exist: {model_dir}", file=sys.stderr)
        print(f"Creating model directory: {model_dir}", file=sys.stderr)
        os.makedirs(model_dir, exist_ok=True)
    
    if not os.path.exists(PIPER_MODEL_PATH):
        print(f"ERROR: Model file not found at {PIPER_MODEL_PATH}", file=sys.stderr)
        print(f"Model directory contents: {os.listdir(model_dir) if os.path.exists(model_dir) else 'N/A'}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"To fix this, download the model file:", file=sys.stderr)
        print(f"  docker exec -it tangerina-piper-tts bash -c 'cd /app/models && wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx'", file=sys.stderr)
        print(f"  docker exec -it tangerina-piper-tts bash -c 'cd /app/models && wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json'", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Or mount a volume with the model file already present.", file=sys.stderr)
        print(f"Server will start but TTS requests will fail until model is available.", file=sys.stderr)
    
    app.run(host="0.0.0.0", port=5001, debug=False)

