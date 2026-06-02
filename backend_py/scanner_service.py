from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ScannerMode = Literal["summary", "full"]
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


def command_for_mode(mode: ScannerMode) -> list[str]:
    npm = npm_executable()
    if mode == "summary":
        return [npm, "run", "multi:periods", "--", "--from-reports", "--summary-only"]
    if mode == "full":
        return [npm, "run", "multi:periods"]
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
    supportedModes: list[str] = field(default_factory=lambda: ["summary", "full"])
    modeNotes: dict[str, str] = field(
        default_factory=lambda: {
            "summary": "Rebuild combined summaries from existing reports; no download.",
            "full": "Run the existing Node multi-period scanner; may download market data.",
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
            return asdict(
                ScannerSnapshot(
                    active=self._active_process is not None,
                    lastJob=asdict(self._last_job) if self._last_job else None,
                )
            )

    def start(self, mode: ScannerMode = "summary") -> dict:
        command = command_for_mode(mode)
        job = ScannerJob(
            id=str(uuid.uuid4()),
            mode=mode,
            status="running",
            command=command,
            startedAt=utc_now_iso(),
            note="Python backend is orchestrating the existing Node scanner.",
        )

        with self._lock:
            if self._active_process is not None:
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
