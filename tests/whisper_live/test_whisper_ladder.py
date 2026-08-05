from __future__ import annotations

import os

import pytest

from features.voice.whisper_diagnose import DiagnoseConfig, WhisperVerdict, run_ladder

pytestmark = pytest.mark.whisper_live


def _live_enabled() -> bool:
    return os.getenv("WHISPER_LIVE", "").strip().lower() in {"1", "true", "yes"}


@pytest.fixture
def diagnose_config():
    if not _live_enabled():
        pytest.skip("WHISPER_LIVE not set")
    cfg = DiagnoseConfig.from_env()
    cfg = DiagnoseConfig(
        api_url=cfg.api_url,
        container_name=cfg.container_name,
        golden_wav=cfg.golden_wav,
        golden_text=cfg.golden_text,
        skip_docker=True,
        restart_loop_threshold=cfg.restart_loop_threshold,
        transcribe_timeout_s=cfg.transcribe_timeout_s,
    )
    cfg.validate()
    return cfg


def test_ladder_proves_sidecar_local_model(diagnose_config):
    report = run_ladder(diagnose_config, warm=True)
    assert report.verdict is WhisperVerdict.PROVEN, report.detail
    assert report.transcript
