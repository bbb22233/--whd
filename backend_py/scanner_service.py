from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ScannerMode = Literal["summary", "full", "node_full", "python_summary", "python_router", "python_research", "python_data", "python_full"]
ScannerStatus = Literal["idle", "running", "succeeded", "failed", "cancelled"]


class ScannerAlreadyRunning(RuntimeError):
    pass


class ScannerCommandUnavailable(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tail_text(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def npm_executable() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise ScannerCommandUnavailable("npm executable not found in PATH")
    return npm


def split_csv_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def scanner_scope_args(symbols: str | None = None, bars: str | None = None) -> list[str]:
    args: list[str] = []
    symbol_values = split_csv_values(symbols)
    bar_values = split_csv_values(bars)
    if symbol_values:
        args.extend(["--symbols", *symbol_values])
    if bar_values:
        args.extend(["--bars", ",".join(bar_values)])
    return args


def command_for_mode(mode: ScannerMode, *, symbols: str | None = None, bars: str | None = None) -> list[str]:
    if mode == "summary":
        npm = npm_executable()
        return [npm, "run", "multi:periods", "--", "--from-reports", "--summary-only", *scanner_scope_args(symbols, bars)]
    if mode == "full":
        scope = scanner_scope_args(symbols, bars or "1D,4H,8H")
        return [
            sys.executable,
            "-m",
            "backend_py.run_full_pipeline",
            "--skip-download",
            "--official",
            "--days",
            "3650",
            *scope,
        ]
    if mode == "node_full":
        npm = npm_executable()
        return [npm, "run", "multi:periods"]
    if mode == "python_summary":
        scope = scanner_scope_args(symbols or "BTC-USDT", bars or "1D")
        return [
            sys.executable,
            "-m",
            "backend_py.build_summary",
            "--from-reports",
            "--summary-only",
            *scope,
        ]
    if mode == "python_router":
        scope = scanner_scope_args(symbols or "BTC-USDT", bars or "1D")
        return [
            sys.executable,
            "-m",
            "backend_py.run_router_parity",
            *scope,
        ]
    if mode == "python_research":
        scope = scanner_scope_args(symbols or "BTC-USDT", bars or "1D")
        return [
            sys.executable,
            "-m",
            "backend_py.run_research_parity",
            *scope,
        ]
    if mode == "python_data":
        scope = scanner_scope_args(symbols or "BTC-USDT", bars or "1D")
        return [
            sys.executable,
            "-m",
            "backend_py.run_data_pipeline",
            *scope,
        ]
    if mode == "python_full":
        scope = scanner_scope_args(symbols or "BTC-USDT", bars or "1D")
        return [
            sys.executable,
            "-m",
            "backend_py.run_full_pipeline",
            *scope,
        ]
    raise ValueError(f"Unsupported scanner mode: {mode}")


@dataclass
class ScannerJob:
    id: str
    mode: ScannerMode
    status: ScannerStatus
    command: list[str]
    startedAt: str
    finishedAt: str | None = None
    pid: int | None = None
    returnCode: int | None = None
    stdoutTail: str = ""
    stderrTail: str = ""
    error: str | None = None
    note: str | None = None


@dataclass
class ScannerSnapshot:
    active: bool
    lastJob: dict | None
    supportedModes: list[str] = field(default_factory=lambda: ["summary", "full", "node_full", "python_summary", "python_router", "python_research", "python_data", "python_full"])
    modeNotes: dict[str, str] = field(
        default_factory=lambda: {
            "summary": "Rebuild combined summaries from existing reports; no download.",
            "full": "Run the Python official full pipeline from existing raw/clean inputs and write production reports.",
            "node_full": "Run the legacy Node multi-period scanner; may download market data.",
            "python_summary": "Run Python from-reports summary parity; defaults to BTC-USDT 1D and writes _py artifacts only.",
            "python_router": "Run Python full router parity against existing Node reports; defaults to BTC-USDT 1D and writes _py artifacts only.",
            "python_research": "Run Python feature/deviation/router/summary parity chain; defaults to BTC-USDT 1D and writes _py artifacts only.",
            "python_data": "Run Python OKX download and clean pipeline; defaults to BTC-USDT 1D and writes data/raw + data/clean.",
            "python_full": "Run Python download/clean/research/summary orchestration; defaults to BTC-USDT 1D and writes _py_full report artifacts unless --official is used from CLI.",
        }
    )


class ScannerService:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or PROJECT_ROOT
        self._lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None
        self._last_job: ScannerJob | None = None

    def snapshot(self) -> dict:
        with self._lock:
            active = self._active_process is not None or self._last_job is not None and self._last_job.status == "running"
            return asdict(
                ScannerSnapshot(
                    active=active,
                    lastJob=asdict(self._last_job) if self._last_job else None,
                )
            )

    def start(self, mode: ScannerMode = "summary", *, symbols: str | None = None, bars: str | None = None) -> dict:
        command = command_for_mode(mode, symbols=symbols, bars=bars)
        job = ScannerJob(
            id=str(uuid.uuid4()),
            mode=mode,
            status="running",
            command=command,
            startedAt=utc_now_iso(),
            note=(
                "Python backend is running a Python parity path."
                if mode in {"full", "python_summary", "python_router", "python_research", "python_data", "python_full"}
                else "Python backend is orchestrating the existing Node scanner."
            ),
        )

        with self._lock:
            if self._active_process is not None or self._last_job is not None and self._last_job.status == "running":
                raise ScannerAlreadyRunning("A scanner job is already running")
            self._last_job = job

        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()
        return asdict(job)

    def cancel(self) -> dict:
        with self._lock:
            process = self._active_process
            job = self._last_job
            if process is None or job is None:
                return {"cancelled": False, "reason": "no active scanner job", "lastJob": asdict(job) if job else None}
            process.terminate()
            job.status = "cancelled"
            job.finishedAt = utc_now_iso()
            job.note = "Cancellation requested by API."
            return {"cancelled": True, "lastJob": asdict(job)}

    def _run_job(self, job: ScannerJob) -> None:
        try:
            process = subprocess.Popen(
                job.command,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self._lock:
                self._active_process = process
                job.pid = process.pid

            stdout, stderr = process.communicate()
            job.returnCode = process.returncode
            job.stdoutTail = tail_text(stdout or "")
            job.stderrTail = tail_text(stderr or "")

            if job.status != "cancelled":
                job.status = "succeeded" if process.returncode == 0 else "failed"
        except Exception as error:  # noqa: BLE001 - record the operational failure for the API.
            job.status = "failed"
            job.error = str(error)
        finally:
            job.finishedAt = job.finishedAt or utc_now_iso()
            with self._lock:
                self._active_process = None
