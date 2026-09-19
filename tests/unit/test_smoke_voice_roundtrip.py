import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'smoke_voice_roundtrip.sh'


def _bash_env(extra_env=None):
    env = os.environ.copy()
    if extra_env:
        for key, value in extra_env.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    return env


def _run_helpers(body, extra_env=None):
    prelude = SCRIPT.read_text().split('\nstatus=0', 1)[0]
    return subprocess.run(
        ['bash', '-c', prelude + '\n' + body],
        capture_output=True,
        text=True,
        env=_bash_env(extra_env),
        check=False,
    )


def _run_driver(stubs, extra_env=None):
    prelude, rest = SCRIPT.read_text().split('\nstatus=0', 1)
    return subprocess.run(
        ['bash', '-c', prelude + '\n' + stubs + '\nstatus=0' + rest],
        capture_output=True,
        text=True,
        env=_bash_env(extra_env),
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

    def test_json_bot_preview_defaults_provider_to_piper(self):
        phrase = 'Olá, Tangerina'
        result = _run_helpers(
            'json_bot_preview',
            extra_env={'SMOKE_PHRASE': phrase},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip())
        assert payload == {'text': phrase, 'provider': 'piper'}

    def test_json_tts_text_uses_default_phrase_when_unset(self):
        result = _run_helpers('json_tts_text', extra_env={'SMOKE_PHRASE': None})
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip())
        assert payload == {'text': 'Olá, este é um teste de voz do Tangerina.'}

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

    def test_parse_transcript_json_missing_text_is_empty(self):
        result = _run_helpers(
            'printf %s \'{}\' | parse_transcript_json',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ''

    def test_parse_transcript_json_invalid_json_fails(self):
        result = _run_helpers(
            "printf %s 'not-json' | parse_transcript_json",
        )
        assert result.returncode != 0

    def test_fuzzy_match_accepts_reordered_long_tokens(self):
        result = _run_helpers(
            'fuzzy_match "teste tangerina voz" "voz extra teste tangerina"',
        )
        assert result.returncode == 0, result.stderr

    def test_fuzzy_match_ignores_short_tokens_but_requires_long_ones(self):
        accepted = _run_helpers(
            'fuzzy_match "um teste de voz" "teste voz"',
        )
        rejected = _run_helpers(
            'fuzzy_match "um teste de voz" "algo diferente"',
        )
        assert accepted.returncode == 0, accepted.stderr
        assert rejected.returncode == 1

    def test_service_urls_strip_base_url_slash_and_use_default_ports(self):
        result = _run_helpers(
            'printf "%s\\n" "$BASE_URL" "$PIPER_URL" "$WHISPER_URL" "$OMNIVOICE_URL" "$BOT_URL"',
            extra_env={
                'BASE_URL': 'http://voice.example/',
                'PIPER_URL': None,
                'WHISPER_URL': None,
                'OMNIVOICE_URL': None,
                'BOT_URL': None,
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'http://voice.example',
            'http://voice.example:5001',
            'http://voice.example:5002',
            'http://voice.example:5003',
            'http://voice.example:5000',
        ]

    def test_explicit_service_urls_override_base_url(self):
        result = _run_helpers(
            'printf "%s\\n" "$PIPER_URL" "$WHISPER_URL" "$OMNIVOICE_URL" "$BOT_URL"',
            extra_env={
                'BASE_URL': 'http://voice.example',
                'PIPER_URL': 'http://piper.local:9',
                'WHISPER_URL': 'http://whisper.local:8',
                'OMNIVOICE_URL': 'http://omnivoice.local:7',
                'BOT_URL': 'http://bot.local:6',
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'http://piper.local:9',
            'http://whisper.local:8',
            'http://omnivoice.local:7',
            'http://bot.local:6',
        ]

    def test_sidecar_roundtrip_rejects_empty_wav(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  if [[ -n "$out" ]]; then
    : > "$out"
  fi
}
run_sidecar_roundtrip piper http://piper.test
''',
        )
        assert result.returncode == 1
        assert 'empty WAV' in result.stderr

    def test_sidecar_roundtrip_passes_when_transcript_matches(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  if [[ -n "$out" ]]; then
    printf 'RIFF' > "$out"
    return 0
  fi
  printf '%s' '{"text":"Olá, este é um teste de voz do Tangerina."}'
}
run_sidecar_roundtrip piper http://piper.test
''',
        )
        assert result.returncode == 0, result.stderr
        assert 'PASS: [piper] sidecar TTS+STT roundtrip' in result.stdout

    def test_sidecar_roundtrip_fails_when_transcript_mismatches(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  if [[ -n "$out" ]]; then
    printf 'RIFF' > "$out"
    return 0
  fi
  printf '%s' '{"text":"algo completamente diferente"}'
}
run_sidecar_roundtrip piper http://piper.test
''',
        )
        assert result.returncode == 1
        assert 'did not match expected phrase' in result.stderr

    def test_sidecar_roundtrip_fails_when_tts_curl_fails(self):
        result = _run_helpers(
            '''
curl() { return 1; }
run_sidecar_roundtrip piper http://piper.test
''',
        )
        assert result.returncode == 1
        assert 'TTS request failed' in result.stderr

    def test_sidecar_roundtrip_fails_when_stt_curl_fails(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  if [[ -n "$out" ]]; then
    printf 'RIFF' > "$out"
    return 0
  fi
  return 1
}
run_sidecar_roundtrip piper http://piper.test
''',
        )
        assert result.returncode == 1

    def test_bot_roundtrip_rejects_empty_wav(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then
      out="$2"
      shift 2
      continue
    fi
    shift
  done
  if [[ -n "$out" ]]; then
    : > "$out"
  fi
}
run_bot_roundtrip
''',
        )
        assert result.returncode == 1
        assert 'empty WAV from /tts/preview' in result.stderr

    def test_bot_roundtrip_passes_when_transcript_matches(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  local url=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      http*) url="$1"; shift ;;
      *) shift ;;
    esac
  done
  if [[ -n "$out" ]]; then
    [[ "$url" == *"/tts/preview" ]] || { echo "unexpected tts url $url" >&2; return 1; }
    printf 'RIFF' > "$out"
    return 0
  fi
  [[ "$url" == *"/stt/transcribe" ]] || { echo "unexpected stt url $url" >&2; return 1; }
  printf '%s' '{"text":"Olá, este é um teste de voz do Tangerina."}'
}
run_bot_roundtrip
''',
        )
        assert result.returncode == 0, result.stderr
        assert 'PASS: [bot] Flask preview TTS+STT roundtrip' in result.stdout

    def test_bot_roundtrip_fails_when_preview_curl_fails(self):
        result = _run_helpers(
            '''
curl() { return 1; }
run_bot_roundtrip
''',
        )
        assert result.returncode == 1
        assert '/tts/preview request failed' in result.stderr

    def test_bot_roundtrip_fails_when_transcript_mismatches(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  local url=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      http*) url="$1"; shift ;;
      *) shift ;;
    esac
  done
  if [[ -n "$out" ]]; then
    printf 'RIFF' > "$out"
    return 0
  fi
  printf '%s' '{"text":"algo completamente diferente"}'
}
run_bot_roundtrip
''',
        )
        assert result.returncode == 1
        assert 'did not match expected phrase' in result.stderr

    def test_bot_roundtrip_fails_when_stt_curl_fails(self):
        result = _run_helpers(
            '''
curl() {
  local out=""
  local url=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      http*) url="$1"; shift ;;
      *) shift ;;
    esac
  done
  if [[ -n "$out" ]]; then
    printf 'RIFF' > "$out"
    return 0
  fi
  return 1
}
run_bot_roundtrip
''',
        )
        assert result.returncode == 1

    def test_driver_runs_only_piper_sidecar_by_default(self):
        result = _run_driver(
            '''
run_sidecar_roundtrip() { echo "sidecar:$1:$2"; return 0; }
run_bot_roundtrip() { echo bot; return 0; }
''',
            extra_env={
                'BASE_URL': None,
                'PIPER_URL': None,
                'WHISPER_URL': None,
                'OMNIVOICE_URL': None,
                'BOT_URL': None,
                'RUN_OMNIVOICE': None,
                'USE_BOT': None,
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'sidecar:piper:http://127.0.0.1:5001',
            'Voice smoke: PASS',
        ]

    def test_driver_runs_omnivoice_and_bot_when_flags_set(self):
        result = _run_driver(
            '''
run_sidecar_roundtrip() { echo "sidecar:$1:$2"; return 0; }
run_bot_roundtrip() { echo bot; return 0; }
''',
            extra_env={
                'BASE_URL': None,
                'PIPER_URL': None,
                'WHISPER_URL': None,
                'OMNIVOICE_URL': None,
                'BOT_URL': None,
                'RUN_OMNIVOICE': '1',
                'USE_BOT': '1',
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'sidecar:piper:http://127.0.0.1:5001',
            'sidecar:omnivoice:http://127.0.0.1:5003',
            'bot',
            'Voice smoke: PASS',
        ]

    def test_driver_ignores_optional_flags_unless_exactly_one(self):
        result = _run_driver(
            '''
run_sidecar_roundtrip() { echo "sidecar:$1:$2"; return 0; }
run_bot_roundtrip() { echo bot; return 0; }
''',
            extra_env={
                'BASE_URL': None,
                'PIPER_URL': None,
                'WHISPER_URL': None,
                'OMNIVOICE_URL': None,
                'BOT_URL': None,
                'RUN_OMNIVOICE': 'true',
                'USE_BOT': 'yes',
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'sidecar:piper:http://127.0.0.1:5001',
            'Voice smoke: PASS',
        ]

    def test_driver_continues_optional_roundtrips_after_piper_failure(self):
        result = _run_driver(
            '''
run_sidecar_roundtrip() { echo "sidecar:$1"; return 1; }
run_bot_roundtrip() { echo bot; return 0; }
''',
            extra_env={
                'BASE_URL': None,
                'PIPER_URL': None,
                'WHISPER_URL': None,
                'OMNIVOICE_URL': None,
                'BOT_URL': None,
                'RUN_OMNIVOICE': '1',
                'USE_BOT': '1',
            },
        )
        assert result.returncode == 1
        assert 'sidecar:piper' in result.stdout
        assert 'sidecar:omnivoice' in result.stdout
        assert 'bot' in result.stdout
        assert 'Voice smoke: FAIL' in result.stderr
