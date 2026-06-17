import re

_JOIN_VOICE_REQUEST_RE = re.compile(
    r"(?:\b(?:entra|entre|entrar|join|conecta|conectar)\b).{0,40}(?:chamada|canal|voice|voz|call)"
    r"|(?:chamada|canal\s+de\s+voz).{0,20}\b(?:entra|entre|join)\b",
    re.IGNORECASE,
)
_JOIN_VOICE_VERB_RE = re.compile(
    r"\b(entra|entre|entrar|join|conecta|conectar)\b",
    re.IGNORECASE,
)
_JOIN_VOICE_NEGATION_RE = re.compile(r"\b(não|nao|nunca|jamais|sem)\s*$", re.IGNORECASE)
_JOIN_VOICE_HOW_TO_RE = re.compile(r"\bcomo\s+entrar\b", re.IGNORECASE)
_JOIN_VOICE_CLAIM_RE = re.compile(
    r"\b(entrei|entrou|joining|joined|conectei|conectado)\b.{0,40}\b(chamada|canal|voice|voz|call)\b",
    re.IGNORECASE,
)


def is_join_voice_request(message: str) -> bool:
    text = message.strip()
    if not text:
        return False
    if _JOIN_VOICE_HOW_TO_RE.search(text):
        return False
    match = _JOIN_VOICE_REQUEST_RE.search(text)
    if not match:
        return False
    verb_match = _JOIN_VOICE_VERB_RE.search(match.group())
    if verb_match and _JOIN_VOICE_NEGATION_RE.search(text[: match.start() + verb_match.start()]):
        return False
    return True


def text_claims_voice_join(text: str) -> bool:
    return bool(_JOIN_VOICE_CLAIM_RE.search(text.strip()))
