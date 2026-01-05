#!/usr/bin/env python3
import os
import tempfile
import logging

from flask import Flask, jsonify, request

try:
    import whisper
except ImportError:
    whisper = None

app = Flask(__name__)
logger = logging.getLogger(__name__)

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "medium")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")
WHISPER_PORT = int(os.getenv("WHISPER_PORT", "5002"))

_model = None


def _load_model():
    global _model
    if _model is None:
        if whisper is None:
            raise RuntimeError("whisper not available")
        _model = whisper.load_model(WHISPER_MODEL_NAME)
    return _model


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/transcribe", methods=["POST"])
def transcribe():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"error": "Missing 'file' upload"}), 400

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        language_param = WHISPER_LANGUAGE if WHISPER_LANGUAGE else None
        result = _load_model().transcribe(tmp_path, language=language_param)
        text_response = result.get("text", "").strip()
        logger.info(f"Transcribe response: {text_response}")
        return jsonify({"text": text_response}), 200
    except Exception as exc:
        logger.error(f"Error transcribing audio: {exc}")
        return jsonify({"error": str(exc)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WHISPER_PORT, debug=False)
