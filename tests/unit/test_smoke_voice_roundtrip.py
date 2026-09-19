import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'smoke_voice_roundtrip.sh'


def _run_helpers(body, extra_env=None):
    prelude = SCRIPT.read_text().split('\nstatus=0', 1)[0]
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ['bash', '-c', prelude + '\n' + body],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.unit
class TestSmokeVoiceRoundtripHelpers:
    def test_json_tts_text_keeps_comma_in_phrase(self):
        phrase = 'Olá, este é um teste de voz do Tangerina.'
        result = _run_helpers('json_tts_text', extra_env={'SMOKE_PHRASE': phrase})
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip())
        assert payload == {'text': phrase}

    def test_json_bot_preview_includes_provider(self):
        phrase = 'Olá, Tangerina'
        result = _run_helpers(
            'json_bot_preview piper',
            extra_env={'SMOKE_PHRASE': phrase},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip())
        assert payload == {'text': phrase, 'provider': 'piper'}

    def test_normalize_text_strips_accents_and_punctuation(self):
        result = _run_helpers(
            'normalize_text "Olá, este é um TESTE!"',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'ola este e um teste'

    def test_fuzzy_match_accepts_accent_and_case_drift(self):
        result = _run_helpers(
            'fuzzy_match "Olá, este é um teste de voz do Tangerina." "OLA este e um teste de voz do tangerina"',
        )
        assert result.returncode == 0, result.stderr

    def test_fuzzy_match_accepts_extra_words_around_expected(self):
        result = _run_helpers(
            'fuzzy_match "teste de voz" "prefixo teste de voz sufixo"',
        )
        assert result.returncode == 0, result.stderr

    def test_fuzzy_match_accepts_truncated_transcript(self):
        result = _run_helpers(
            'fuzzy_match "ola este e um teste de voz do tangerina" "este e um teste de voz"',
        )
        assert result.returncode == 0, result.stderr

    def test_fuzzy_match_rejects_empty_transcript(self):
        result = _run_helpers('fuzzy_match "Olá Tangerina" ""')
        assert result.returncode == 1

    def test_fuzzy_match_requires_long_tokens(self):
        result = _run_helpers(
            'fuzzy_match "teste tangerina voz" "algo completamente diferente"',
        )
        assert result.returncode == 1

    def test_parse_transcript_json_reads_text(self):
        result = _run_helpers(
            'printf %s \'{"text": "  transcrito  "}\' | parse_transcript_json',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'transcrito'
