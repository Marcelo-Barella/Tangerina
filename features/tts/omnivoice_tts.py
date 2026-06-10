import os
import logging
import tempfile
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class OmnivoiceTTS:
    def __init__(self, api_url: Optional[str] = None, timeout: Optional[int] = None):
        self.api_url = (api_url or os.getenv("OMNIVOICE_API_URL", "")).rstrip("/")
        if not self.api_url:
            raise RuntimeError("OMNIVOICE_API_URL is required for OmniVoice TTS")
        if requests is None:
            raise RuntimeError("requests library is required for OmniVoice HTTP mode")
        self.timeout = timeout or int(os.getenv("OMNIVOICE_TIMEOUT", "90"))
        logger.info("OmnivoiceTTS initialized: %s", self.api_url)

    def _ensure_output_path(self, output_path: Optional[str]) -> str:
        if output_path:
            return output_path
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        path = temp_file.name
        temp_file.close()
        return path

    def _cleanup_file(self, path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def generate_speech(self, text: str, output_path: Optional[str] = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        output_path = self._ensure_output_path(output_path)

        try:
            response = requests.post(
                f"{self.api_url}/tts",
                json={"text": text},
                timeout=self.timeout,
                stream=True,
            )

            if response.status_code != 200:
                try:
                    error_msg = response.json().get("error", f"HTTP {response.status_code}")
                except ValueError:
                    error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
                self._cleanup_file(output_path)
                raise RuntimeError(f"OmniVoice TTS API error: {error_msg}")

            with open(output_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    handle.write(chunk)

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("Received empty or invalid audio file from OmniVoice TTS API")

            return output_path
        except requests.exceptions.Timeout:
            self._cleanup_file(output_path)
            raise RuntimeError("TTS generation timed out")
        except requests.exceptions.ConnectionError as exc:
            self._cleanup_file(output_path)
            raise RuntimeError(f"Failed to connect to OmniVoice TTS API at {self.api_url}: {exc}")
        except requests.exceptions.RequestException as exc:
            self._cleanup_file(output_path)
            raise RuntimeError(f"OmniVoice TTS API request failed: {exc}")
        except Exception:
            self._cleanup_file(output_path)
            raise
