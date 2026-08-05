#!/usr/bin/env python3
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from flask import Flask, jsonify, request

from features.voice.openai_whisper_api import (
    DEFAULT_WHISPER_LANGUAGE,
    TRANSCRIPTION_TIMEOUT,
    build_openai_whisper_client,
    transcribe_openai_whisper,
)

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
except ImportError:
    FasterWhisperModel = None

try:
    import whisper
except ImportError:
    whisper = None

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "").strip()
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", DEFAULT_WHISPER_LANGUAGE)
WHISPER_PORT = int(os.getenv("WHISPER_PORT", "5002"))
WHISPER_INITIAL_PROMPT = os.getenv("WHISPER_INITIAL_PROMPT", "")
WHISPER_LOCAL_ENGINE = (os.getenv("WHISPER_LOCAL_ENGINE") or "faster-whisper").strip().lower()
WHISPER_DEVICE = (os.getenv("WHISPER_DEVICE") or "cpu").strip()
WHISPER_COMPUTE_TYPE = (os.getenv("WHISPER_COMPUTE_TYPE") or "int8").strip()
WHISPER_USE_OPENAI_API = (os.getenv("WHISPER_USE_OPENAI_API") or "").strip().lower()

_openai_client = None
_transcribe_lock = threading.Lock()

class ModelPhase(Enum):
    COLD = "cold"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"

@dataclass
class LocalModelGate:
    phase: ModelPhase = ModelPhase.COLD
    model_name: str = WHISPER_MODEL_NAME
    engine: str = WHISPER_LOCAL_ENGINE
    load_ms: Optional[float] = None
    last_error: Optional[str] = None
    _model: Any = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.phase.value,
                "model_loaded": self.phase is ModelPhase.READY and self._model is not None,
                "model": self.model_name,
                "engine": self.engine,
                "load_ms": self.load_ms,
                "last_error": self.last_error,
            }

    def load_if_needed(self, loader) -> Any:
        with self._lock:
            if self._model is not None and self.phase is ModelPhase.READY:
                return self._model
            self.phase = ModelPhase.LOADING
            self.last_error = None
            started = time.monotonic()
            try:
                model = loader()
            except Exception as exc:
                self.phase = ModelPhase.ERROR
                self.last_error = str(exc)
                self._model = None
                raise
            self._model = model
            self.load_ms = (time.monotonic() - started) * 1000.0
            self.phase = ModelPhase.READY
            self.last_error = None
            return self._model

_local_gate = LocalModelGate()

def _use_openai_api() -> bool:
    if not OPENAI_API_KEY:
        return False
    if WHISPER_USE_OPENAI_API in {"0", "false", "no"}:
        return False
    if WHISPER_USE_OPENAI_API in {"1", "true", "yes"}:
        return True
    if OPENAI_BASE_URL:
        return False
    return True

def _normalized_local_engine() -> str:
    if WHISPER_LOCAL_ENGINE in {"openai-whisper", "openai_whisper", "whisper"}:
        return "openai-whisper"
    return "faster-whisper"

def _local_backend_available() -> bool:
    if _normalized_local_engine() == "openai-whisper":
        return whisper is not None
    return FasterWhisperModel is not None

def _local_provider_name() -> str:
    return _normalized_local_engine()

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = build_openai_whisper_client(OPENAI_API_KEY, timeout=TRANSCRIPTION_TIMEOUT)
    return _openai_client

def _load_local_model():
    engine = _normalized_local_engine()
    _local_gate.engine = engine
    if engine == "openai-whisper":
        if whisper is None:
            raise RuntimeError("openai-whisper package not available")
        return whisper.load_model(WHISPER_MODEL_NAME)
    if FasterWhisperModel is None:
        raise RuntimeError("faster-whisper package not available")
    return FasterWhisperModel(
        WHISPER_MODEL_NAME,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )

def _transcribe_openai_whisper_local(model: Any, tmp_path: str, language: str | None, prompt: str) -> str:
    transcribe_kwargs = {}
    if language:
        transcribe_kwargs["language"] = language
    if prompt:
        transcribe_kwargs["initial_prompt"] = prompt
    result = model.transcribe(tmp_path, **transcribe_kwargs)
    return result.get("text", "").strip()

def _transcribe_faster_whisper(model: Any, tmp_path: str, language: str | None, prompt: str) -> str:
    kwargs = {"beam_size": 5, "vad_filter": True}
    if language:
        kwargs["language"] = language
    if prompt:
        kwargs["initial_prompt"] = prompt
    segments, info = model.transcribe(tmp_path, **kwargs)
    segment_rows = []
    texts = []
    for segment in segments:
        texts.append(segment.text)
        segment_rows.append({
            "start": getattr(segment, "start", None),
            "end": getattr(segment, "end", None),
            "text": (segment.text or "")[:120],
        })
    text = "".join(texts).strip()
    return text

def _transcribe_local(tmp_path: str, language: str | None, prompt: str) -> str:
    model = _local_gate.load_if_needed(_load_local_model)
    if _normalized_local_engine() == "openai-whisper":
        return _transcribe_openai_whisper_local(model, tmp_path, language, prompt)
    return _transcribe_faster_whisper(model, tmp_path, language, prompt)

@app.route("/health", methods=["GET"])
def health():
    if _use_openai_api():
        return jsonify({"status": "ok", "provider": "openai-api"}), 200
    if not _local_backend_available():
        return jsonify({
            "status": "error",
            "error": f"No transcription backend available for engine {_local_provider_name()}",
            "provider": _local_provider_name(),
        }), 503
    return jsonify({"status": "ok", "provider": _local_provider_name()}), 200

@app.route("/ready", methods=["GET"])
def ready():
    if _use_openai_api():
        return jsonify({
            "state": "ready",
            "provider": "openai-api",
            "model_loaded": True,
        }), 200

    warm = request.args.get("warm", "").strip() in {"1", "true", "yes"}
    if warm:
        try:
            _local_gate.load_if_needed(_load_local_model)
        except Exception:
            snap = _local_gate.snapshot()
            snap["provider"] = _local_provider_name()
            return jsonify(snap), 503

    snap = _local_gate.snapshot()
    snap["provider"] = _local_provider_name()
    if snap["state"] == ModelPhase.READY.value and snap["model_loaded"]:
        return jsonify(snap), 200
    return jsonify(snap), 503

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
        t0 = time.monotonic()
        with _transcribe_lock:
            if _use_openai_api():
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
    if _use_openai_api():
        logger.info("Whisper sidecar using OpenAI Whisper API (whisper-1)")
    else:
        logger.info(
            "Whisper sidecar using local engine=%s model=%s device=%s compute_type=%s",
            _local_provider_name(),
            WHISPER_MODEL_NAME,
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
    app.run(host="0.0.0.0", port=WHISPER_PORT, debug=False)
