import os
import tempfile
from typing import Optional

try:
    import requests
except ImportError:
    requests = None


class HttpTTSClient:
    def __init__(self, api_url: str, timeout: int, provider_name: str):
        self.api_url = api_url.rstrip("/")
        if not self.api_url:
            raise RuntimeError(f"API URL is required for {provider_name} HTTP mode")
        self.timeout = timeout
        self.provider_name = provider_name

    def generate_speech(self, text: str, output_path: Optional[str] = None) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        return generate_speech_via_http(
            self.api_url, text, self.timeout, self.provider_name, output_path
        )


def create_omnivoice_client(
    api_url: Optional[str] = None, timeout: Optional[int] = None
) -> HttpTTSClient:
    url = (api_url or os.getenv("OMNIVOICE_API_URL", "")).rstrip("/")
    if not url:
        raise RuntimeError("OMNIVOICE_API_URL is required for OmniVoice TTS")
    return HttpTTSClient(
        url,
        timeout or int(os.getenv("OMNIVOICE_TIMEOUT", "90")),
        "OmniVoice",
    )


def ensure_output_path(output_path: Optional[str]) -> str:
    if output_path:
        return output_path
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    path = temp_file.name
    temp_file.close()
    return path


def cleanup_tts_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def generate_speech_via_http(
    api_url: str,
    text: str,
    timeout: int,
    provider_name: str,
    output_path: Optional[str] = None,
) -> str:
    if requests is None:
        raise RuntimeError(f"requests library is required for {provider_name} HTTP mode")

    output_path = ensure_output_path(output_path)

    try:
        response = requests.post(
            f"{api_url.rstrip('/')}/tts",
            json={"text": text},
            timeout=timeout,
            stream=True,
        )

        if response.status_code != 200:
            try:
                error_msg = response.json().get("error", f"HTTP {response.status_code}")
            except ValueError:
                error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
            raise RuntimeError(f"{provider_name} TTS API error: {error_msg}")

        with open(output_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                handle.write(chunk)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Received empty or invalid audio file from {provider_name} TTS API")

        return output_path
    except requests.exceptions.Timeout:
        raise RuntimeError("TTS generation timed out")
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Failed to connect to {provider_name} TTS API at {api_url}: {exc}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"{provider_name} TTS API request failed: {exc}")
    except Exception:
        cleanup_tts_file(output_path)
        raise
