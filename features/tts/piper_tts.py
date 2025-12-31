import os
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

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

    def _ensure_output_path(self, output_path: Optional[str]) -> str:
        if output_path:
            return output_path
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        output_path = temp_file.name
        temp_file.close()
        return output_path

    def _cleanup_file(self, path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _generate_via_http(self, text: str, output_path: Optional[str] = None) -> str:
        output_path = self._ensure_output_path(output_path)
        
        try:
            response = requests.post(
                f"{self.api_url.rstrip('/')}/tts",
                json={"text": text},
                timeout=30,
                stream=True
            )
            
            if response.status_code != 200:
                try:
                    error_msg = response.json().get("error", f"HTTP {response.status_code}")
                except ValueError:
                    error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
                raise RuntimeError(f"Piper TTS API error: {error_msg}")
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("Received empty or invalid audio file from Piper TTS API")
            
            return output_path
            
        except requests.exceptions.Timeout:
            raise RuntimeError("TTS generation timed out")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Failed to connect to Piper TTS API at {self.api_url}: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Piper TTS API request failed: {e}")
        except Exception:
            self._cleanup_file(output_path)
            raise

    def _generate_via_subprocess(self, text: str, output_path: Optional[str] = None) -> str:
        output_path = self._ensure_output_path(output_path)
        
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
            self._cleanup_file(output_path)
            raise

    def generate_speech(self, text: str, output_path: Optional[str] = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        if self.use_http:
            return self._generate_via_http(text, output_path)
        return self._generate_via_subprocess(text, output_path)
