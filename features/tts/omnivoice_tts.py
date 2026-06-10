import os
import logging
from typing import Optional

from features.tts.http_tts import generate_speech_via_http

logger = logging.getLogger(__name__)


class OmnivoiceTTS:
    def __init__(self, api_url: Optional[str] = None, timeout: Optional[int] = None):
        self.api_url = (api_url or os.getenv("OMNIVOICE_API_URL", "")).rstrip("/")
        if not self.api_url:
            raise RuntimeError("OMNIVOICE_API_URL is required for OmniVoice TTS")
        self.timeout = timeout or int(os.getenv("OMNIVOICE_TIMEOUT", "90"))
        logger.info("OmnivoiceTTS initialized: %s", self.api_url)

    def generate_speech(self, text: str, output_path: Optional[str] = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        return generate_speech_via_http(
            self.api_url, text, self.timeout, "OmniVoice", output_path
        )
