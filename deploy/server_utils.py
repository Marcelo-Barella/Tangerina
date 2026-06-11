import os
from typing import Optional, Tuple

from flask import Response, after_this_request, jsonify, request

from sanitize_text import sanitize_text


def safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def register_temp_cleanup(path: str) -> None:
    @after_this_request
    def _remove(response):
        safe_remove(path)
        return response


def parse_tts_text_request() -> Tuple[Optional[str], Optional[Tuple[Response, int]]]:
    payload = request.get_json(silent=True)
    if not payload:
        return None, (jsonify({"error": "Missing JSON body"}), 400)
    if "text" not in payload:
        return None, (jsonify({"error": "Missing 'text' field"}), 400)

    text = payload["text"]
    if not isinstance(text, str) or not text.strip():
        return None, (jsonify({"error": "Text must be a non-empty string"}), 400)

    text = sanitize_text(text)
    if not text:
        return None, (jsonify({"error": "Text contains only unsupported characters"}), 400)

    return text, None
