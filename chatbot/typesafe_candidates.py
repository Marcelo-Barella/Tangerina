import re
from typing import Dict, List

from chatbot.typesafe_settings import MUSIC_COMMAND_KEYWORDS

_PLAY_STRIP = re.compile(
    r"\b(toca|play|tocar|tangerina)\b",
    re.IGNORECASE,
)
_VOLUME_DIGITS = re.compile(r"\b(\d{1,3})\b")
_SEARCH_PREFIX = re.compile(
    r"^(pesquisa|pesquisar|busca|buscar|procura|procurar)\s+",
    re.IGNORECASE,
)


def music_play_query_candidates(message: str, max_candidates: int = 6) -> Dict[str, str]:
    text = message.strip()
    if not text:
        return {}
    candidates: List[str] = []
    stripped = _PLAY_STRIP.sub("", text).strip(" ,.")
    if stripped:
        candidates.append(stripped)
    for token in text.split():
        cleaned = token.strip(" ,.")
        if len(cleaned) >= 3 and cleaned.lower() not in MUSIC_COMMAND_KEYWORDS:
            if cleaned not in candidates:
                candidates.append(cleaned)
    if text not in candidates:
        candidates.insert(0, text)
    out: Dict[str, str] = {}
    for idx, value in enumerate(candidates[:max_candidates]):
        key = f"q{idx}"
        out[key] = value
    return out


def volume_candidates(message: str) -> Dict[str, str]:
    matches = _VOLUME_DIGITS.findall(message)
    out: Dict[str, str] = {}
    for idx, raw in enumerate(matches[:5]):
        out[f"v{idx}"] = raw
    return out


def web_search_query_candidates(message: str, max_candidates: int = 5) -> Dict[str, str]:
    text = message.strip()
    if not text:
        return {}
    candidates: List[str] = []
    without_prefix = _SEARCH_PREFIX.sub("", text).strip()
    if without_prefix:
        candidates.append(without_prefix)
    if text not in candidates:
        candidates.insert(0, text)
    out: Dict[str, str] = {}
    for idx, value in enumerate(candidates[:max_candidates]):
        out[f"s{idx}"] = value
    return out
