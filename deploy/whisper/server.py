#!/usr/bin/env python3
import os
import tempfile
import logging
import threading

from flask import Flask, jsonify, request

from features.voice.openai_whisper_api import (
    DEFAULT_WHISPER_LANGUAGE,
    TRANSCRIPTION_TIMEOUT,
    build_openai_whisper_client,
    transcribe_openai_whisper,
)

try:
    import whisper
except ImportError:
    whisper = None

app = Flask(__name__)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", DEFAULT_WHISPER_LANGUAGE)
WHISPER_PORT = int(os.getenv("WHISPER_PORT", "5002"))
WHISPER_INITIAL_PROMPT = os.getenv("WHISPER_INITIAL_PROMPT", "")

_openai_client = None
_local_model = None
_transcribe_lock = threading.Lock()


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = build_openai_whisper_client(OPENAI_API_KEY, timeout=TRANSCRIPTION_TIMEOUT)
    return _openai_client


def _load_local_model():
    global _local_model
    if _local_model is None:
        if whisper is None:
            raise RuntimeError("openai-whisper package not available")
        _local_model = whisper.load_model(WHISPER_MODEL_NAME)
    return _local_model


def _transcribe_local(tmp_path: str, language: str | None, prompt: str) -> str:
    transcribe_kwargs = {}
    if language:
        transcribe_kwargs["language"] = language
    if prompt:
        transcribe_kwargs["initial_prompt"] = prompt
    result = _load_local_model().transcribe(tmp_path, **transcribe_kwargs)
    return result.get("text", "").strip()


@app.route("/health", methods=["GET"])
def health():
    if OPENAI_API_KEY:
        return jsonify({"status": "ok", "provider": "openai-api"}), 200
    if whisper is None:
        return jsonify({"status": "error", "error": "No transcription backend available"}), 503
    return jsonify({"status": "ok", "provider": "local"}), 200


@app.route("/transcribe", methods=["POST"])
def transcribe():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"error": "Missing 'file' upload"}), 400

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            uploaded.save(tmp.name)
            tmp_path = tmp.name

        language_param = WHISPER_LANGUAGE if WHISPER_LANGUAGE else None
        prompt = (request.form.get("prompt") or WHISPER_INITIAL_PROMPT or "").strip()
        with _transcribe_lock:
            if OPENAI_API_KEY:
                with open(tmp_path, "rb") as audio_file:
                    text_response = transcribe_openai_whisper(
                        _get_openai_client(),
                        audio_file,
                        language=language_param,
                        prompt=prompt or None,
                    )
            else:
                text_response = _transcribe_local(tmp_path, language_param, prompt)
        logger.info(f"Transcribe response: {text_response}")
        return jsonify({"text": text_response}), 200
    except Exception as exc:
        logger.error(f"Error transcribing audio: {exc}")
        return jsonify({"error": str(exc)}), 500
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    if OPENAI_API_KEY:
        logger.info("Whisper sidecar using OpenAI Whisper API (whisper-1)")
    else:
        logger.warning(
            "OPENAI_API_KEY not set; falling back to local openai-whisper model %s",
            WHISPER_MODEL_NAME,
        )
    app.run(host="0.0.0.0", port=WHISPER_PORT, debug=False)
