#!/usr/bin/env python3
import logging
import os
import re
import sys
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple

import soundfile as sf
import torch
from flask import Flask, Response, jsonify, request, send_file

from model_loader import load_omnivoice_model

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_model_state: Optional[Dict[str, Any]] = None
_model_lock = threading.Lock()
_load_error: Optional[str] = None


def sanitize_text(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _warmup_model() -> None:
    global _model_state, _load_error
    try:
        _model_state = load_omnivoice_model()
        instruct = os.getenv("OMNIVOICE_INSTRUCT", "female, brazilian accent")
        model = _model_state["model"]
        logger.info("Warming up OmniVoice with voice design instruct=%r", instruct)
        model.generate(
            text="warmup",
            instruct=instruct,
            num_step=int(os.getenv("OMNIVOICE_NUM_STEP", "16")),
            speed=float(os.getenv("OMNIVOICE_SPEED", "1.0")),
        )
        logger.info("OmniVoice warmup complete")
    except Exception as exc:
        _load_error = str(exc)
        logger.exception("Failed to load OmniVoice model: %s", exc)


def _get_model_state() -> Dict[str, Any]:
    if _model_state is None:
        raise RuntimeError(_load_error or "Model is not loaded yet")
    return _model_state


def _generate_audio(text: str):
    state = _get_model_state()
    model = state["model"]
    device = state["device"]
    instruct = os.getenv("OMNIVOICE_INSTRUCT", "female, brazilian accent")
    kwargs = {
        "text": text,
        "instruct": instruct,
        "num_step": int(os.getenv("OMNIVOICE_NUM_STEP", "16")),
        "speed": float(os.getenv("OMNIVOICE_SPEED", "1.0")),
    }
    try:
        return model.generate(**kwargs)
    except RuntimeError as exc:
        if "out of memory" not in str(exc).lower() or not str(device).startswith("cuda"):
            raise
        logger.warning("CUDA OOM during generation, retrying on CPU: %s", exc)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        try:
            model.to("cpu")
        except Exception:
            pass
        return model.generate(**kwargs)


@app.route("/health", methods=["GET"])
def health() -> Tuple[Response, int]:
    if _load_error:
        return jsonify({"status": "error", "error": _load_error}), 503
    if _model_state is None:
        return jsonify({"status": "loading"}), 503

    return jsonify(
        {
            "status": "ok",
            "device": _model_state["device"],
            "precision": _model_state["precision"],
            "model": _model_state["model_id"],
            "instruct": os.getenv("OMNIVOICE_INSTRUCT", "female, brazilian accent"),
            "vram_estimate_gb": _model_state["vram_estimate_gb"],
        }
    ), 200


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

    text = sanitize_text(text)
    if not text:
        return jsonify({"error": "Text contains only unsupported characters"}), 400

    try:
        with _model_lock:
            audio = _generate_audio(text)
    except RuntimeError as exc:
        if _load_error or _model_state is None:
            return jsonify({"error": _load_error or "Model is not loaded yet"}), 503
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        logger.exception("TTS generation failed: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if not audio:
        return jsonify({"error": "No audio generated"}), 500

    waveform = audio[0] if isinstance(audio, list) else audio

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        output_path = tmp_file.name

    try:
        sf.write(output_path, waveform, 24000)
        return send_file(
            output_path,
            mimetype="audio/wav",
            as_attachment=True,
            download_name="output.wav",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("OMNIVOICE_PORT", "5003"))
    loader_thread = threading.Thread(target=_warmup_model, daemon=True)
    loader_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
