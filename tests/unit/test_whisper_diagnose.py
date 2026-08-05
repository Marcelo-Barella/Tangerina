from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from features.voice.whisper_diagnose import (
    DiagnoseConfig,
    DockerEvidence,
    ReadyState,
    TranscribeEvidence,
    WhisperVerdict,
    golden_matches,
    normalize_tokens,
    parse_ready_payload,
    remediation_for,
    run_ladder,
    wer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_WAV = REPO_ROOT / "tests" / "fixtures" / "whisper" / "pt_tangerina.wav"
GOLDEN_TXT = REPO_ROOT / "tests" / "fixtures" / "whisper" / "pt_tangerina.golden.txt"


def _cfg(**overrides: Any) -> DiagnoseConfig:
    base = DiagnoseConfig(
        api_url="http://127.0.0.1:5002",
        container_name="whisper-asr",
        golden_wav=GOLDEN_WAV,
        golden_text=GOLDEN_TXT,
        skip_docker=False,
        restart_loop_threshold=3,
        transcribe_timeout_s=120.0,
    )
    if not overrides:
        return base
    data = base.__dict__.copy()
    data.update(overrides)
    return DiagnoseConfig(**data)


class FakeDocker:
    def __init__(self, evidence: DockerEvidence) -> None:
        self.evidence = evidence

    def inspect(self, container_name: str) -> DockerEvidence:
        return self.evidence


class FakeHttp:
    def __init__(
        self,
        *,
        health: tuple[int, Mapping[str, Any]] | Exception = (200, {"status": "ok", "provider": "local"}),
        ready: tuple[int, Mapping[str, Any]] | Exception = (
            200,
            {"state": "ready", "provider": "local", "model_loaded": True, "model": "tiny"},
        ),
        transcribe: TranscribeEvidence | Exception | None = None,
    ) -> None:
        self.health = health
        self.ready = ready
        self.transcribe = transcribe or TranscribeEvidence(
            http_status=200,
            timed_out=False,
            transcript="tangerina tocar musica",
            latency_ms=10.0,
            error_body=None,
        )

    def get_json(self, url: str, timeout_s: float) -> tuple[int, Mapping[str, Any]]:
        if url.rstrip("/").endswith("health"):
            if isinstance(self.health, Exception):
                raise self.health
            return self.health
        if "ready" in url:
            if isinstance(self.ready, Exception):
                raise self.ready
            return self.ready
        raise AssertionError(f"unexpected GET {url}")

    def post_multipart_wav(
        self,
        url: str,
        wav_path: Path,
        prompt: str,
        timeout_s: float,
    ) -> TranscribeEvidence:
        if isinstance(self.transcribe, Exception):
            raise self.transcribe
        return self.transcribe


def _running_docker(**kwargs: Any) -> DockerEvidence:
    base = dict(
        container_name="whisper-asr",
        exists=True,
        running=True,
        oom_killed=False,
        exit_code=0,
        restart_count=0,
        status="running",
    )
    base.update(kwargs)
    return DockerEvidence(**base)


@pytest.mark.unit
def test_normalize_and_wer_and_wake_word():
    assert normalize_tokens("Tangerina, tocar!") == ["tangerina", "tocar"]
    assert wer("tangerina tocar musica", "tangerina tocar musica") == 0.0
    assert wer("tangerina tocar", "tangerina tocar musica") == pytest.approx(1 / 3)
    assert golden_matches("tangerina tocar musica", "tangerina tocar musica")
    assert not golden_matches("tocar musica agora", "tangerina tocar musica")
    assert not golden_matches("banana tocar musica xyz abc", "tangerina tocar musica", max_wer=0.0)


@pytest.mark.unit
def test_parse_ready_payload():
    ev = parse_ready_payload(200, {"state": "ready", "provider": "local", "model_loaded": True, "load_ms": 12.5})
    assert ev.state is ReadyState.READY
    assert ev.model_loaded is True
    assert ev.load_ms == 12.5


@pytest.mark.unit
def test_container_missing():
    docker = FakeDocker(_running_docker(exists=False, running=False, status="missing"))
    report = run_ladder(_cfg(), docker=docker, http=FakeHttp())
    assert report.verdict is WhisperVerdict.CONTAINER_MISSING
    assert remediation_for(report.verdict)


@pytest.mark.unit
def test_restart_loop_threshold_and_oom():
    docker = FakeDocker(_running_docker(restart_count=3))
    report = run_ladder(_cfg(), docker=docker, http=FakeHttp())
    assert report.verdict is WhisperVerdict.RESTART_LOOP

    docker = FakeDocker(_running_docker(restart_count=1, oom_killed=True, exit_code=137))
    report = run_ladder(_cfg(), docker=docker, http=FakeHttp())
    assert report.verdict is WhisperVerdict.RESTART_LOOP


@pytest.mark.unit
def test_unreachable():
    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(health=ConnectionError("refused")),
    )
    assert report.verdict is WhisperVerdict.UNREACHABLE


@pytest.mark.unit
def test_shallow_ok_model_cold_and_loading():
    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(ready=(503, {"state": "cold", "provider": "local", "model_loaded": False})),
    )
    assert report.verdict is WhisperVerdict.SHALLOW_OK_MODEL_COLD

    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(ready=(503, {"state": "loading", "provider": "local", "model_loaded": False})),
    )
    assert report.verdict is WhisperVerdict.LOADING


@pytest.mark.unit
def test_provider_not_local():
    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(ready=(200, {"state": "ready", "provider": "openai-api", "model_loaded": True})),
    )
    assert report.verdict is WhisperVerdict.PROVIDER_NOT_LOCAL
    assert "ready" in report.stages_completed


@pytest.mark.unit
def test_transcribe_failures_and_proven():
    base_ready = (200, {"state": "ready", "provider": "local", "model_loaded": True, "model": "tiny"})
    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(
            ready=base_ready,
            transcribe=TranscribeEvidence(500, False, None, 1.0, "boom"),
        ),
    )
    assert report.verdict is WhisperVerdict.TRANSCRIBE_HTTP_ERROR

    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(
            ready=base_ready,
            transcribe=TranscribeEvidence(None, True, None, 1.0, "timeout"),
        ),
    )
    assert report.verdict is WhisperVerdict.TRANSCRIBE_TIMEOUT

    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(
            ready=base_ready,
            transcribe=TranscribeEvidence(200, False, None, 1.0, None),
        ),
    )
    assert report.verdict is WhisperVerdict.EMPTY_TRANSCRIPT

    report = run_ladder(
        _cfg(skip_docker=True),
        http=FakeHttp(
            ready=base_ready,
            transcribe=TranscribeEvidence(200, False, "banana xyz", 1.0, None),
        ),
    )
    assert report.verdict is WhisperVerdict.GOLDEN_MISMATCH

    report = run_ladder(
        _cfg(skip_docker=True),
        docker=FakeDocker(_running_docker()),
        http=FakeHttp(ready=base_ready),
    )
    assert report.verdict is WhisperVerdict.PROVEN
    assert report.remediation is None


@pytest.mark.unit
def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WHISPER_API_URL", raising=False)
    monkeypatch.delenv("WHISPER_TRANSCRIPTION_TIMEOUT", raising=False)
    cfg = DiagnoseConfig.from_env({})
    assert cfg.api_url == "http://127.0.0.1:5002"
    assert cfg.container_name == "whisper-asr"
    assert cfg.restart_loop_threshold == 3
    assert cfg.transcribe_timeout_s == 120.0
    assert cfg.golden_wav.name == "pt_tangerina.wav"
