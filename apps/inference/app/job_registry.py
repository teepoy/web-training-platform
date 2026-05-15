from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

JOB_STATES = frozenset({"pending", "running", "completed", "failed", "cancelled", "lost"})
ACTIVE_STATES = frozenset({"pending", "running"})
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "lost"})


@dataclass
class JobRecord:
    """In-memory representation of a GPU training job."""

    gpu_job_id: str
    platform_job_id: str
    status: str
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    updated_at: float = field(default_factory=time.time)
    progress: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the runtime-contract GET /v1/train/{job_id} response shape."""

        def _ts(v: float | None) -> str | None:
            if v is None:
                return None
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()

        return {
            "job_id": self.gpu_job_id,
            "platform_job_id": self.platform_job_id,
            "status": self.status,
            "progress": self.progress,
            "metrics": self.metrics,
            "error": self.error,
            "created_at": _ts(self.created_at),
            "started_at": _ts(self.started_at),
            "updated_at": _ts(self.updated_at),
        }


class JobConflictError(Exception):
    """Raised when a training job conflict occurs (single-job constraint or terminal state cancel)."""


class JobRegistry:
    """V1 in-memory job registry.

    All state is lost on restart.  The Prefect worker is responsible for
    detecting lost jobs and marking platform jobs as failed.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._by_platform_id: dict[str, str] = {}

    # ── submission ────────────────────────────────────────────────

    def submit(self, platform_job_id: str) -> tuple[JobRecord, bool]:
        """Submit a new training job.

        Returns:
            (record, is_duplicate) — is_duplicate is True when the same
            platform_job_id was already submitted (idempotent resubmit).
        Raises:
            JobConflictError: when a different training job is already active.
        """
        # Idempotent resubmit — same platform_job_id already known
        if platform_job_id in self._by_platform_id:
            gpu_id = self._by_platform_id[platform_job_id]
            return self._jobs[gpu_id], True

        # Single active training job constraint
        for job in self._jobs.values():
            if job.status in ACTIVE_STATES:
                raise JobConflictError(
                    "A training job is already running. "
                    "Only one training job may be active at a time."
                )

        gpu_job_id = str(uuid.uuid4())
        now = time.time()
        record = JobRecord(
            gpu_job_id=gpu_job_id,
            platform_job_id=platform_job_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self._jobs[gpu_job_id] = record
        self._by_platform_id[platform_job_id] = gpu_job_id
        return record, False

    # ── lookup ────────────────────────────────────────────────────

    def get(self, gpu_job_id: str) -> JobRecord | None:
        return self._jobs.get(gpu_job_id)

    def get_by_platform_id(self, platform_job_id: str) -> JobRecord | None:
        gpu_id = self._by_platform_id.get(platform_job_id)
        if gpu_id is None:
            return None
        return self._jobs.get(gpu_id)

    # ── lifecycle ─────────────────────────────────────────────────

    def update_status(self, gpu_job_id: str, status: str, **kwargs: Any) -> JobRecord:
        """Transition a job to a new status.  Sets started_at on first pending→running."""
        job = self._jobs.get(gpu_job_id)
        if job is None:
            raise KeyError(f"Job {gpu_job_id} not found")
        if status not in JOB_STATES:
            raise ValueError(f"Invalid status: {status}")
        if job.status == "pending" and status == "running" and job.started_at is None:
            job.started_at = time.time()
        job.status = status
        job.updated_at = time.time()
        for k, v in kwargs.items():
            if hasattr(job, k):
                setattr(job, k, v)
        return job

    def cancel(self, gpu_job_id: str) -> JobRecord:
        """Cancel a job.  Raises JobConflictError if already terminal."""
        job = self._jobs.get(gpu_job_id)
        if job is None:
            raise KeyError(f"Job {gpu_job_id} not found")
        if job.status in TERMINAL_STATES:
            raise JobConflictError(f"Job is in terminal state: {job.status}")
        job.status = "cancelled"
        job.updated_at = time.time()
        return job

    # ── logs ──────────────────────────────────────────────────────

    def append_log(self, gpu_job_id: str, level: str, message: str) -> None:
        job = self._jobs.get(gpu_job_id)
        if job is None:
            raise KeyError(f"Job {gpu_job_id} not found")
        job.logs.append(
            {
                "timestamp": time.time(),
                "level": level,
                "message": message,
            }
        )

    def get_logs(self, gpu_job_id: str, tail: int = 100) -> list[dict[str, Any]]:
        job = self._jobs.get(gpu_job_id)
        if job is None:
            raise KeyError(f"Job {gpu_job_id} not found")
        entries = job.logs[-tail:] if tail > 0 else job.logs
        return [
            {
                "timestamp": datetime.fromtimestamp(
                    e["timestamp"], tz=timezone.utc
                ).isoformat(),
                "level": e["level"],
                "message": e["message"],
            }
            for e in entries
        ]

    # ── queries ───────────────────────────────────────────────────

    def has_active_training(self) -> bool:
        return any(j.status in ACTIVE_STATES for j in self._jobs.values())

    def get_active_job(self) -> JobRecord | None:
        for job in self._jobs.values():
            if job.status in ACTIVE_STATES:
                return job
        return None

    def mark_all_lost(self) -> None:
        """Mark all active jobs as lost.  Called on worker restart."""
        now = time.time()
        for job in self._jobs.values():
            if job.status in ACTIVE_STATES:
                job.status = "lost"
                job.updated_at = now
