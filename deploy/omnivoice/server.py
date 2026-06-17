#!/usr/bin/env python3
import logging
import os
import tempfile
import threading
from typing import Any, Dict, Optional, Tuple

import soundfile as sf
import torch
from flask import Flask, Response, after_this_request, jsonify, request, send_file

from model_loader import load_omnivoice_model
from sanitize_text import sanitize_text, unlink_temp

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_model_state: Optional[Dict[str, Any]] = None
_model_ready = False
_model_lock = threading.Lock()
_load_error: Optional[str] = None
_hung_inference_thread: Optional[threading.Thread] = None
_DEFAULT_INSTRUCT = "female, portuguese accent"


class InferenceTimeout(TimeoutError):
    def __init__(self, thread: threading.Thread) -> None:
        super().__init__("TTS generation timed out")
        self.thread = thread


def _generation_kwargs(text: str) -> Dict[str, Any]:
    return {
        "text": text,
        "instruct": os.getenv("OMNIVOICE_INSTRUCT", _DEFAULT_INSTRUCT),
        "num_step": int(os.getenv("OMNIVOICE_NUM_STEP", "16")),
        "speed": float(os.getenv("OMNIVOICE_SPEED", "1.0")),
    }


def _warmup_model() -> None:
    global _model_state, _model_ready, _load_error
    try:
        _model_state = load_omnivoice_model()
        model = _model_state["model"]
        kwargs = _generation_kwargs("warmup")
        logger.info("Warming up OmniVoice with voice design instruct=%r", kwargs["instruct"])
        with _model_lock:
            model.generate(**kwargs)
        _model_ready = True
        logger.info("OmniVoice warmup complete")
    except Exception as exc:
        _load_error = str(exc)
        logger.exception("Failed to load OmniVoice model: %s", exc)


def _get_model_state() -> Dict[str, Any]:
    if _model_state is None:
        raise RuntimeError(_load_error or "Model is not loaded yet")
    if not _model_ready:
        raise RuntimeError("Model is still warming up")
    return _model_state


def _inference_timeout_seconds() -> int:
    return int(os.getenv("OMNIVOICE_TIMEOUT", "90"))


def _blocked_by_hung_inference() -> bool:
    global _hung_inference_thread
    if _hung_inference_thread is None:
        return False
    if not _hung_inference_thread.is_alive():
        _hung_inference_thread = None
        return False
    return True


def _generate_audio(text: str):
    state = _get_model_state()
    model = state["model"]
    device = state["device"]
    kwargs = _generation_kwargs(text)
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
            return model.generate(**kwargs)
        finally:
            try:
                model.to(device)
            except Exception:
                logger.warning("Failed to restore model to %s after CPU retry", device)


def _generate_audio_timed(text: str):
    audio_output: list = []
    generation_error: list = []

    def _run() -> None:
        try:
            audio_output.append(_generate_audio(text))
        except Exception as exc:
            generation_error.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(_inference_timeout_seconds())
    if thread.is_alive():
        raise InferenceTimeout(thread)
    if generation_error:
        raise generation_error[0]
    return audio_output[0]


@app.route("/health", methods=["GET"])
def health() -> Tuple[Response, int]:
    if _load_error:
        return jsonify({"status": "error", "error": _load_error}), 503
    if _model_state is None or not _model_ready:
        return jsonify({"status": "loading"}), 503
    if _blocked_by_hung_inference():
        return jsonify(
            {
                "status": "recovering",
                "error": "TTS service is recovering from a prior timeout",
            }
        ), 503

    return jsonify(
        {
            "status": "ok",
            "device": _model_state["device"],
            "precision": _model_state["precision"],
            "model": _model_state["model_id"],
            "instruct": os.getenv("OMNIVOICE_INSTRUCT", _DEFAULT_INSTRUCT),
            "vram_estimate_gb": _model_state["vram_estimate_gb"],
        }
    ), 200


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

    if _blocked_by_hung_inference():
        return jsonify({"error": "TTS service is recovering from a prior timeout"}), 503

    try:
        with _model_lock:
            if _blocked_by_hung_inference():
                return jsonify({"error": "TTS service is recovering from a prior timeout"}), 503
            try:
                audio = _generate_audio_timed(text)
            except InferenceTimeout as exc:
                global _hung_inference_thread
                _hung_inference_thread = exc.thread
                logger.error(
                    "TTS inference timed out after %ss; blocking new requests until thread exits",
                    _inference_timeout_seconds(),
                )
                return jsonify({"error": "TTS generation timed out"}), 504
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
    except Exception as exc:
        unlink_temp(output_path)
        return jsonify({"error": str(exc)}), 500

    @after_this_request
    def _remove_temp_file(response):
        unlink_temp(output_path)
        return response

    return send_file(
        output_path,
        mimetype="audio/wav",
        as_attachment=True,
        download_name="output.wav",
    )


if __name__ == "__main__":
    port = int(os.getenv("OMNIVOICE_PORT", "5003"))
    loader_thread = threading.Thread(target=_warmup_model, daemon=True)
    loader_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
