import os
import logging
import subprocess
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

from features.tts.http_tts import cleanup_tts_file, ensure_output_path, generate_speech_via_http

logger = logging.getLogger(__name__)


class PiperTTS:
    def __init__(self, model_path: Optional[str] = None, piper_bin: Optional[str] = None):
        self.api_url = os.getenv("PIPER_API_URL")
        self.use_http = bool(self.api_url)
        
        if self.use_http:
            if requests is None:
                raise RuntimeError("requests library is required for HTTP API mode. Install with: pip install requests")
            logger.info(f"PiperTTS initialized in HTTP API mode: {self.api_url}")
            return
        
        self.model_path = model_path or os.getenv("PIPER_MODEL_PATH") or self._find_default_model()
        self.piper_bin = piper_bin or os.getenv("PIPER_BIN") or self._find_piper_executable()
        logger.info("PiperTTS initialized in direct subprocess mode")

    def _find_default_model(self) -> str:
        base_path = Path.home() / ".piper" / "models"
        candidates = [base_path / "pt_BR-faber-medium.onnx", base_path / "pt_BR-faber-low.onnx"]
        
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0])

    def _find_piper_executable(self) -> str:
        for path in ["/usr/local/bin/piper", "/usr/bin/piper", str(Path.home() / ".local" / "bin" / "piper"), "piper"]:
            if self._check_executable(path):
                return path
        raise RuntimeError("Piper executable not found")

    def _check_executable(self, path: str) -> bool:
        try:
            result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    def _generate_via_subprocess(self, text: str, output_path: Optional[str] = None) -> str:
        output_path = ensure_output_path(output_path)
        
        try:
            process = subprocess.run(
                [self.piper_bin, "--model", self.model_path, "--output_file", output_path],
                input=text,
                text=True,
                capture_output=True,
                timeout=30,
            )
            
            if process.returncode != 0:
                stderr = (process.stderr or "").strip()
                raise RuntimeError(stderr or "piper failed")
            
            return output_path
        except subprocess.TimeoutExpired:
            raise RuntimeError("TTS generation timed out")
        except Exception:
            cleanup_tts_file(output_path)
            raise

    def generate_speech(self, text: str, output_path: Optional[str] = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        if self.use_http:
            return generate_speech_via_http(self.api_url, text, 30, "Piper", output_path)
        return self._generate_via_subprocess(text, output_path)
