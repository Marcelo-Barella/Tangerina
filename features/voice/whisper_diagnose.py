from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class WhisperVerdict(Enum):
    CONTAINER_MISSING = "container_missing"
    RESTART_LOOP = "restart_loop"
    UNREACHABLE = "unreachable"
    SHALLOW_OK_MODEL_COLD = "shallow_ok_model_cold"
    LOADING = "loading"
    READY_UNPROVEN = "ready_unproven"
    TRANSCRIBE_HTTP_ERROR = "transcribe_http_error"
    TRANSCRIBE_TIMEOUT = "transcribe_timeout"
    EMPTY_TRANSCRIPT = "empty_transcript"
    GOLDEN_MISMATCH = "golden_mismatch"
    PROVIDER_NOT_LOCAL = "provider_not_local"
    PROVEN = "proven"


class ReadyState(Enum):
    MISSING_BACKEND = "missing_backend"
    COLD = "cold"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class DockerEvidence:
    container_name: str
    exists: bool
    running: bool
    oom_killed: bool
    exit_code: Optional[int]
    restart_count: int
    status: str


@dataclass(frozen=True)
class HealthEvidence:
    ok: bool
    http_status: int
    provider: Optional[str]
    body: Mapping[str, Any]


@dataclass(frozen=True)
class ReadyEvidence:
    http_status: int
    state: ReadyState
    provider: Optional[str]
    model_name: Optional[str]
    model_loaded: bool
    load_ms: Optional[float]
    last_error: Optional[str]
    stats: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscribeEvidence:
    http_status: Optional[int]
    timed_out: bool
    transcript: Optional[str]
    latency_ms: Optional[float]
    error_body: Optional[str]


@dataclass(frozen=True)
class WhisperReport:
    verdict: WhisperVerdict
    api_url: str
    stages_completed: Sequence[str]
    docker: Optional[DockerEvidence] = None
    health: Optional[HealthEvidence] = None
    ready: Optional[ReadyEvidence] = None
    transcribe: Optional[TranscribeEvidence] = None
    transcript: Optional[str] = None
    detail: str = ""
    remediation: Optional[str] = None


@dataclass(frozen=True)
class DiagnoseConfig:
    api_url: str
    container_name: str
    golden_wav: Path
    golden_text: Path
    skip_docker: bool
    restart_loop_threshold: int
    transcribe_timeout_s: float

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "DiagnoseConfig":
        env = environ if environ is not None else os.environ
        repo_root = Path(__file__).resolve().parents[2]
        default_wav = repo_root / "tests" / "fixtures" / "whisper" / "pt_tangerina.wav"
        default_golden = repo_root / "tests" / "fixtures" / "whisper" / "pt_tangerina.golden.txt"
        timeout_raw = (env.get("WHISPER_TRANSCRIPTION_TIMEOUT") or "120").strip()
        threshold_raw = (env.get("WHISPER_RESTART_LOOP_THRESHOLD") or "3").strip()
        return cls(
            api_url=(env.get("WHISPER_API_URL") or "http://127.0.0.1:5002").rstrip("/"),
            container_name=(env.get("WHISPER_CONTAINER_NAME") or "whisper-asr").strip(),
            golden_wav=Path(env.get("WHISPER_GOLDEN_WAV") or default_wav),
            golden_text=Path(env.get("WHISPER_GOLDEN_TEXT") or default_golden),
            skip_docker=(env.get("WHISPER_SKIP_DOCKER") or "").strip().lower() in {"1", "true", "yes"},
            restart_loop_threshold=int(threshold_raw),
            transcribe_timeout_s=float(timeout_raw),
        )

    def validate(self) -> None:
        parsed = urlparse(self.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"invalid api_url: {self.api_url!r}")
        if not self.container_name:
            raise ValueError("container_name must be non-empty")
        if self.restart_loop_threshold < 1:
            raise ValueError("restart_loop_threshold must be >= 1")
        if self.transcribe_timeout_s <= 0:
            raise ValueError("transcribe_timeout_s must be > 0")
        if not self.golden_wav.is_file():
            raise FileNotFoundError(f"golden wav missing: {self.golden_wav}")
        if not self.golden_text.is_file():
            raise FileNotFoundError(f"golden text missing: {self.golden_text}")


class DockerPort(Protocol):
    def inspect(self, container_name: str) -> DockerEvidence:
        ...


class HttpPort(Protocol):
    def get_json(self, url: str, timeout_s: float) -> tuple[int, Mapping[str, Any]]:
        ...

    def post_multipart_wav(
        self,
        url: str,
        wav_path: Path,
        prompt: str,
        timeout_s: float,
    ) -> TranscribeEvidence:
        ...


class SubprocessDockerPort:
    def inspect(self, container_name: str) -> DockerEvidence:
        fmt = (
            "{{.State.Running}}\t{{.State.OOMKilled}}\t{{.State.ExitCode}}\t"
            "{{.RestartCount}}\t{{.State.Status}}"
        )
        try:
            proc = subprocess.run(
                ["docker", "inspect", "-f", fmt, container_name],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return DockerEvidence(
                container_name=container_name,
                exists=False,
                running=False,
                oom_killed=False,
                exit_code=None,
                restart_count=0,
                status="docker_missing",
            )
        if proc.returncode != 0:
            return DockerEvidence(
                container_name=container_name,
                exists=False,
                running=False,
                oom_killed=False,
                exit_code=None,
                restart_count=0,
                status="missing",
            )
        parts = proc.stdout.strip().split("\t")
        while len(parts) < 5:
            parts.append("")
        running = parts[0].lower() == "true"
        oom_killed = parts[1].lower() == "true"
        try:
            exit_code = int(parts[2]) if parts[2] != "" else None
        except ValueError:
            exit_code = None
        try:
            restart_count = int(parts[3]) if parts[3] != "" else 0
        except ValueError:
            restart_count = 0
        return DockerEvidence(
            container_name=container_name,
            exists=True,
            running=running,
            oom_killed=oom_killed,
            exit_code=exit_code,
            restart_count=restart_count,
            status=parts[4] or ("running" if running else "exited"),
        )


class RequestsHttpPort:
    def get_json(self, url: str, timeout_s: float) -> tuple[int, Mapping[str, Any]]:
        try:
            import requests
        except ImportError:
            return self._get_json_urllib(url, timeout_s)
        try:
            resp = requests.get(url, timeout=timeout_s)
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(str(exc)) from exc
        try:
            body: Mapping[str, Any] = resp.json() if resp.content else {}
        except ValueError:
            body = {"raw": resp.text}
        return resp.status_code, body

    def post_multipart_wav(
        self,
        url: str,
        wav_path: Path,
        prompt: str,
        timeout_s: float,
    ) -> TranscribeEvidence:
        try:
            import requests
        except ImportError:
            return self._post_multipart_urllib(url, wav_path, prompt, timeout_s)
        started = time.monotonic()
        try:
            with wav_path.open("rb") as handle:
                resp = requests.post(
                    url,
                    files={"file": (wav_path.name, handle, "audio/wav")},
                    data={"prompt": prompt},
                    timeout=timeout_s,
                )
        except requests.exceptions.Timeout as exc:
            return TranscribeEvidence(
                http_status=None,
                timed_out=True,
                transcript=None,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_body=str(exc),
            )
        except requests.exceptions.RequestException as exc:
            return TranscribeEvidence(
                http_status=None,
                timed_out=False,
                transcript=None,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_body=str(exc),
            )
        latency_ms = (time.monotonic() - started) * 1000.0
        transcript = None
        error_body = None
        if resp.status_code == 200:
            try:
                payload = resp.json()
                transcript = str(payload.get("text", "")).strip() or None
            except ValueError:
                error_body = resp.text
        else:
            error_body = resp.text
        return TranscribeEvidence(
            http_status=resp.status_code,
            timed_out=False,
            transcript=transcript,
            latency_ms=latency_ms,
            error_body=error_body,
        )

    def _get_json_urllib(self, url: str, timeout_s: float) -> tuple[int, Mapping[str, Any]]:
        try:
            with urlopen(url, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw}
            return exc.code, body
        except URLError as exc:
            raise ConnectionError(str(exc)) from exc
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return int(status), body

    def _post_multipart_urllib(
        self,
        url: str,
        wav_path: Path,
        prompt: str,
        timeout_s: float,
    ) -> TranscribeEvidence:
        import uuid

        boundary = f"----whisper{uuid.uuid4().hex}"
        wav_bytes = wav_path.read_bytes()
        chunks = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{wav_path.name}"\r\n'.encode(),
            b"Content-Type: audio/wav\r\n\r\n",
            wav_bytes,
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="prompt"\r\n\r\n',
            prompt.encode("utf-8"),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(chunks)
        req = Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                status = int(getattr(resp, "status", 200))
        except TimeoutError as exc:
            return TranscribeEvidence(
                http_status=None,
                timed_out=True,
                transcript=None,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_body=str(exc),
            )
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return TranscribeEvidence(
                http_status=exc.code,
                timed_out=False,
                transcript=None,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_body=raw,
            )
        except URLError as exc:
            reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
            timed_out = "timed out" in reason.lower()
            return TranscribeEvidence(
                http_status=None,
                timed_out=timed_out,
                transcript=None,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_body=reason,
            )
        latency_ms = (time.monotonic() - started) * 1000.0
        transcript = None
        error_body = None
        if status == 200:
            try:
                payload = json.loads(raw)
                transcript = str(payload.get("text", "")).strip() or None
            except json.JSONDecodeError:
                error_body = raw
        else:
            error_body = raw
        return TranscribeEvidence(
            http_status=status,
            timed_out=False,
            transcript=transcript,
            latency_ms=latency_ms,
            error_body=error_body,
        )


def parse_ready_payload(http_status: int, body: Mapping[str, Any]) -> ReadyEvidence:
    state_raw = str(body.get("state") or "").strip().lower()
    try:
        state = ReadyState(state_raw) if state_raw else (
            ReadyState.READY if http_status == 200 else ReadyState.COLD
        )
    except ValueError as exc:
        raise ValueError(f"unknown ready state: {state_raw!r}") from exc
    load_ms_raw = body.get("load_ms")
    load_ms: Optional[float]
    try:
        load_ms = float(load_ms_raw) if load_ms_raw is not None else None
    except (TypeError, ValueError):
        load_ms = None
    stats = body.get("stats") if isinstance(body.get("stats"), Mapping) else {}
    return ReadyEvidence(
        http_status=http_status,
        state=state,
        provider=(str(body["provider"]) if body.get("provider") is not None else None),
        model_name=(str(body["model"]) if body.get("model") is not None else (
            str(body["model_name"]) if body.get("model_name") is not None else None
        )),
        model_loaded=bool(body.get("model_loaded")),
        load_ms=load_ms,
        last_error=(str(body["last_error"]) if body.get("last_error") is not None else None),
        stats=dict(stats),
    )


_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def normalize_tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    parts = _TOKEN_RE.split(stripped)
    return [p for p in parts if p]


def wer(hypothesis: str, reference: str) -> float:
    hyp = normalize_tokens(hypothesis)
    ref = normalize_tokens(reference)
    if not ref:
        return 0.0 if not hyp else 1.0
    rows = len(ref) + 1
    cols = len(hyp) + 1
    dp = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1] / float(len(ref))


def golden_matches(
    transcript: str,
    golden: str,
    *,
    wake_word: str = "tangerina",
    max_wer: float = 0.34,
) -> bool:
    hyp_tokens = normalize_tokens(transcript)
    if wake_word.casefold() not in hyp_tokens:
        return False
    return wer(transcript, golden) <= max_wer


def load_golden_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def remediation_for(verdict: WhisperVerdict) -> Optional[str]:
    return {
        WhisperVerdict.CONTAINER_MISSING: "cd deploy/whisper && docker compose up -d --build",
        WhisperVerdict.RESTART_LOOP: "check WHISPER_MEM_LIMIT / OOM; docker logs whisper-asr; consider WHISPER_MODEL=tiny",
        WhisperVerdict.UNREACHABLE: "confirm WHISPER_API_URL and that whisper-asr is listening on the host port",
        WhisperVerdict.SHALLOW_OK_MODEL_COLD: "GET /ready?warm=1 to load the local model, then re-run",
        WhisperVerdict.LOADING: "wait for model load to finish, then re-run (or poll /ready)",
        WhisperVerdict.READY_UNPROVEN: "re-run without short-circuit; prove stage should continue automatically",
        WhisperVerdict.TRANSCRIBE_HTTP_ERROR: "docker logs whisper-asr; inspect POST /transcribe error body",
        WhisperVerdict.TRANSCRIBE_TIMEOUT: "raise WHISPER_TRANSCRIPTION_TIMEOUT or warm the model first with /ready?warm=1",
        WhisperVerdict.EMPTY_TRANSCRIPT: "verify golden WAV and WHISPER_LANGUAGE; check sidecar logs",
        WhisperVerdict.GOLDEN_MISMATCH: "compare transcript to golden; check model size and language",
        WhisperVerdict.PROVIDER_NOT_LOCAL: "unset OPENAI_API_KEY for local proof (use docker-compose.model-test.yml)",
        WhisperVerdict.PROVEN: None,
    }.get(verdict)


def _report(
    verdict: WhisperVerdict,
    api_url: str,
    stages: Sequence[str],
    *,
    docker: Optional[DockerEvidence] = None,
    health: Optional[HealthEvidence] = None,
    ready: Optional[ReadyEvidence] = None,
    transcribe: Optional[TranscribeEvidence] = None,
    transcript: Optional[str] = None,
    detail: str = "",
) -> WhisperReport:
    return WhisperReport(
        verdict=verdict,
        api_url=api_url,
        stages_completed=tuple(stages),
        docker=docker,
        health=health,
        ready=ready,
        transcribe=transcribe,
        transcript=transcript,
        detail=detail,
        remediation=remediation_for(verdict),
    )


def format_report_table(report: WhisperReport) -> str:
    stage_order = ("docker", "health", "ready", "transcribe")
    completed = set(report.stages_completed)
    fail_stage = {
        WhisperVerdict.CONTAINER_MISSING: "docker",
        WhisperVerdict.RESTART_LOOP: "docker",
        WhisperVerdict.UNREACHABLE: "health",
        WhisperVerdict.SHALLOW_OK_MODEL_COLD: "ready",
        WhisperVerdict.LOADING: "ready",
        WhisperVerdict.TRANSCRIBE_HTTP_ERROR: "transcribe",
        WhisperVerdict.TRANSCRIBE_TIMEOUT: "transcribe",
        WhisperVerdict.EMPTY_TRANSCRIPT: "transcribe",
        WhisperVerdict.GOLDEN_MISMATCH: "transcribe",
        WhisperVerdict.PROVIDER_NOT_LOCAL: "transcribe",
    }.get(report.verdict)
    if report.verdict is WhisperVerdict.UNREACHABLE and "health" in completed:
        fail_stage = "ready" if "ready" not in completed else "transcribe"
    lines = ["STAGE       STATUS  DETAIL"]
    saw_fail = False
    for stage in stage_order:
        if stage == "docker" and "docker" not in completed and report.docker is None:
            status = "SKIP"
            detail = "skip_docker"
        elif saw_fail:
            status = "SKIP"
            detail = "earlier stage failed"
        elif stage == fail_stage:
            status = "FAIL"
            detail = report.detail or report.verdict.value
            saw_fail = True
        elif stage in completed:
            status = "PASS"
            if stage == "docker" and report.docker is not None:
                detail = f"restarts={report.docker.restart_count} status={report.docker.status}"
            elif stage == "health" and report.health is not None:
                detail = f"provider={report.health.provider or '?'}"
            elif stage == "ready" and report.ready is not None:
                detail = f"state={report.ready.state.value} provider={report.ready.provider or '?'}"
            elif stage == "transcribe" and report.transcript is not None:
                detail = report.transcript[:80]
            else:
                detail = ""
        else:
            status = "SKIP"
            detail = "not run"
        lines.append(f"{stage:<11}{status:<7}{detail}")
    lines.append("")
    lines.append(f"VERDICT: {report.verdict.value}")
    if report.remediation:
        lines.append(f"REMEDIATION: {report.remediation}")
    return "\n".join(lines)


def format_report_json(report: WhisperReport) -> str:
    payload = {
        "verdict": report.verdict.value,
        "api_url": report.api_url,
        "stages_completed": list(report.stages_completed),
        "docker": asdict(report.docker) if report.docker else None,
        "health": asdict(report.health) if report.health else None,
        "ready": (
            {
                **{k: v for k, v in asdict(report.ready).items() if k != "state"},
                "state": report.ready.state.value,
            }
            if report.ready
            else None
        ),
        "transcribe": asdict(report.transcribe) if report.transcribe else None,
        "transcript": report.transcript,
        "detail": report.detail,
        "remediation": report.remediation,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def format_report(report: WhisperReport) -> str:
    return format_report_table(report)


def _is_restart_loop(docker: DockerEvidence, threshold: int) -> bool:
    if docker.restart_count >= threshold:
        return True
    if docker.oom_killed and docker.restart_count >= 1:
        return True
    if docker.exit_code == 137 and docker.restart_count >= 1:
        return True
    return False


def run_ladder(
    config: DiagnoseConfig,
    *,
    docker: Optional[DockerPort] = None,
    http: Optional[HttpPort] = None,
    warm: bool = False,
) -> WhisperReport:
    docker_port = docker or SubprocessDockerPort()
    http_port = http or RequestsHttpPort()
    stages: list[str] = []
    docker_ev: Optional[DockerEvidence] = None
    health_ev: Optional[HealthEvidence] = None
    ready_ev: Optional[ReadyEvidence] = None

    if not config.skip_docker:
        docker_ev = docker_port.inspect(config.container_name)
        if not docker_ev.exists:
            return _report(
                WhisperVerdict.CONTAINER_MISSING,
                config.api_url,
                stages,
                docker=docker_ev,
                detail=f"no container named {config.container_name!r}",
            )
        if _is_restart_loop(docker_ev, config.restart_loop_threshold):
            return _report(
                WhisperVerdict.RESTART_LOOP,
                config.api_url,
                stages,
                docker=docker_ev,
                detail=(
                    f"restarts={docker_ev.restart_count} oom={docker_ev.oom_killed} "
                    f"exit={docker_ev.exit_code}"
                ),
            )
        stages.append("docker")

    health_url = urljoin(config.api_url + "/", "health")
    try:
        status, body = http_port.get_json(health_url, timeout_s=10.0)
    except (ConnectionError, TimeoutError, OSError) as exc:
        return _report(
            WhisperVerdict.UNREACHABLE,
            config.api_url,
            stages,
            docker=docker_ev,
            detail=str(exc),
        )
    health_ev = HealthEvidence(
        ok=status == 200,
        http_status=status,
        provider=(str(body["provider"]) if isinstance(body, Mapping) and body.get("provider") is not None else None),
        body=dict(body) if isinstance(body, Mapping) else {"raw": body},
    )
    if status != 200:
        return _report(
            WhisperVerdict.UNREACHABLE,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            detail=f"health HTTP {status}",
        )
    stages.append("health")

    ready_path = "ready?warm=1" if warm else "ready"
    ready_url = urljoin(config.api_url + "/", ready_path)
    try:
        ready_status, ready_body = http_port.get_json(
            ready_url,
            timeout_s=config.transcribe_timeout_s if warm else 10.0,
        )
    except (ConnectionError, TimeoutError, OSError) as exc:
        return _report(
            WhisperVerdict.UNREACHABLE,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            detail=f"ready unreachable: {exc}",
        )
    if not isinstance(ready_body, Mapping):
        ready_body = {"raw": ready_body}
    try:
        ready_ev = parse_ready_payload(ready_status, ready_body)
    except ValueError as exc:
        return _report(
            WhisperVerdict.SHALLOW_OK_MODEL_COLD,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            detail=str(exc),
        )

    if ready_ev.state is ReadyState.LOADING or ready_status == 503 and ready_ev.state is ReadyState.LOADING:
        return _report(
            WhisperVerdict.LOADING,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            detail="model loading",
        )
    if ready_ev.state in {ReadyState.COLD, ReadyState.MISSING_BACKEND, ReadyState.ERROR} or (
        ready_status == 503 and not ready_ev.model_loaded
    ):
        if ready_ev.state is ReadyState.LOADING:
            return _report(
                WhisperVerdict.LOADING,
                config.api_url,
                stages,
                docker=docker_ev,
                health=health_ev,
                ready=ready_ev,
                detail="model loading",
            )
        return _report(
            WhisperVerdict.SHALLOW_OK_MODEL_COLD,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            detail=f"ready state={ready_ev.state.value}",
        )
    stages.append("ready")

    provider = (ready_ev.provider or "").strip().lower()
    if provider == "openai-api":
        return _report(
            WhisperVerdict.PROVIDER_NOT_LOCAL,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            detail="provider is openai-api; PROVEN requires local model",
        )

    golden = load_golden_text(config.golden_text)
    prompt = os.getenv(
        "WHISPER_INITIAL_PROMPT",
        "Transcreva em português brasileiro. tangerina tocar musica.",
    )
    transcribe_url = urljoin(config.api_url + "/", "transcribe")
    tx = http_port.post_multipart_wav(
        transcribe_url,
        config.golden_wav,
        prompt,
        config.transcribe_timeout_s,
    )
    if tx.timed_out:
        return _report(
            WhisperVerdict.TRANSCRIBE_TIMEOUT,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            transcribe=tx,
            detail=tx.error_body or "timeout",
        )
    if tx.http_status is None:
        return _report(
            WhisperVerdict.UNREACHABLE,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            transcribe=tx,
            detail=tx.error_body or "transcribe connect failed",
        )
    if tx.http_status != 200:
        return _report(
            WhisperVerdict.TRANSCRIBE_HTTP_ERROR,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            transcribe=tx,
            detail=f"HTTP {tx.http_status}: {(tx.error_body or '')[:200]}",
        )
    if not tx.transcript:
        return _report(
            WhisperVerdict.EMPTY_TRANSCRIPT,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            transcribe=tx,
            transcript=tx.transcript,
            detail="empty transcript",
        )
    if not golden_matches(tx.transcript, golden):
        return _report(
            WhisperVerdict.GOLDEN_MISMATCH,
            config.api_url,
            stages,
            docker=docker_ev,
            health=health_ev,
            ready=ready_ev,
            transcribe=tx,
            transcript=tx.transcript,
            detail=f"wer={wer(tx.transcript, golden):.2f} text={tx.transcript!r}",
        )
    stages.append("transcribe")
    return _report(
        WhisperVerdict.PROVEN,
        config.api_url,
        stages,
        docker=docker_ev,
        health=health_ev,
        ready=ready_ev,
        transcribe=tx,
        transcript=tx.transcript,
        detail="golden matched",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Whisper verdict ladder")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--warm", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--url", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    cfg = DiagnoseConfig.from_env()
    overrides: dict[str, Any] = {}
    if args.skip_docker:
        overrides["skip_docker"] = True
    if args.url:
        overrides["api_url"] = args.url.rstrip("/")
    if overrides:
        cfg = DiagnoseConfig(**{**asdict(cfg), **overrides})
    cfg.validate()
    report = run_ladder(cfg, warm=args.warm)
    print(format_report_json(report) if args.json else format_report_table(report))
    return 0 if report.verdict is WhisperVerdict.PROVEN else 1


if __name__ == "__main__":
    raise SystemExit(main())
