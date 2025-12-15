#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, Tuple

from flask import Flask, Response, jsonify, request, send_file

app = Flask(__name__)

PIPER_BIN = os.getenv("PIPER_BIN", "/usr/local/bin/piper")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "/app/models/pt_BR-faber-medium.onnx")

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
    
    if not os.path.exists(PIPER_MODEL_PATH):
        print(f"Warning: Model file not found at {PIPER_MODEL_PATH}", file=sys.stderr)
    
    app.run(host="0.0.0.0", port=5001, debug=False)

