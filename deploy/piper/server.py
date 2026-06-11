#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, Tuple

from flask import Flask, Response, after_this_request, jsonify, request, send_file

from sanitize_text import sanitize_text, unlink_temp

app = Flask(__name__)

PIPER_BIN = os.getenv("PIPER_BIN", "/usr/local/bin/piper")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "/app/models/pt_BR-faber-medium.onnx")


@app.route("/health", methods=["GET"])
def health() -> Tuple[Response, int]:
    return jsonify({"status": "ok"}), 200

@app.route("/tts", methods=["POST"])
def tts() -> Tuple[Response, int] | Response:
    payload: Dict[str, Any] | None = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Missing JSON body"}), 400
    if "text" not in payload:
        return jsonify({"error": "Missing 'text' field"}), 400
    
    text = payload["text"]
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Text must be a non-empty string"}), 400
    
    text = sanitize_text(text)
    
    if not text:
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
            unlink_temp(output_path)
            return jsonify({"error": error_msg}), 500

        if not os.path.exists(output_path):
            unlink_temp(output_path)
            return jsonify({"error": "Audio file not generated"}), 500

        @after_this_request
        def _remove_temp_file(response):
            unlink_temp(output_path)
            return response
        
        return send_file(
            output_path,
            mimetype="audio/wav",
            as_attachment=True,
            download_name="output.wav"
        )
    except subprocess.TimeoutExpired:
        unlink_temp(output_path)
        return jsonify({"error": "TTS generation timed out"}), 504
    except Exception as exc:
        unlink_temp(output_path)
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

