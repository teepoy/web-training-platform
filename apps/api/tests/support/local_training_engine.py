from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.shared.api.schemas import ArtifactRef, JobStatus, TrainingEvent, TrainingJob


class LocalProcessEngine:
    """Test-only in-process training engine."""

    def __init__(self, storage: object | None = None) -> None:
        self.storage = storage
        self._runs: dict[str, dict[str, object]] = {}

    async def submit(self, job: TrainingJob) -> str:
        external_id = f"local-{job.id}"
        self._runs[external_id] = {
            "state": "RUNNING",
            "result": None,
            "error": None,
            "cancelled": False,
            "events": [
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="local training accepted",
                    payload={"phase": "accepted"},
                )
            ],
        }
        asyncio.create_task(self._execute(external_id, job))
        return external_id

    async def _execute(self, external_id: str, job: TrainingJob) -> None:
        run = self._runs[external_id]
        if run["cancelled"]:
            run["state"] = "CANCELLED"
            return
        try:
            if job.dataset_id is None and (
                job.collection_id is None or job.collection_revision_id is None
            ):
                raise ValueError(
                    f"Source data for training job '{job.id}' is unavailable"
                )
            events = run["events"]
            assert isinstance(events, list)
            events.append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="local training started",
                    payload={"phase": "running"},
                )
            )
            from app.modules.training.flows.train_job import execute_training_runtime

            result = await execute_training_runtime(
                job_id=job.id,
                dataset_id=job.dataset_id,
                trainer_id=job.trainer_id,
                created_by=job.created_by,
                org_id=job.org_id or "",
                collection_id=job.collection_id,
                collection_revision_id=job.collection_revision_id,
            )
            run["result"] = result
            run["state"] = "COMPLETED"

            metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
            if isinstance(metrics, dict) and metrics:
                events.append(
                    TrainingEvent(
                        job_id=job.id,
                        ts=datetime.now(UTC),
                        level="metric",
                        message="training metrics",
                        payload=dict(metrics),
                    )
                )
                epoch_losses = metrics.get("epoch_losses", [])
                if not isinstance(epoch_losses, list):
                    epoch_losses = []
                for epoch in range(1, int(metrics.get("epochs", 0)) + 1):
                    payload: dict[str, object] = {"epoch": epoch}
                    if epoch - 1 < len(epoch_losses):
                        payload["val/loss"] = float(epoch_losses[epoch - 1])
                    events.append(
                        TrainingEvent(
                            job_id=job.id,
                            ts=datetime.now(UTC),
                            level="epoch",
                            message=f"epoch {epoch} completed",
                            payload=payload,
                        )
                    )
            events.append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="training completed",
                    payload={"status": "completed"},
                )
            )
        except Exception as exc:
            run["error"] = str(exc)
            run["traceback"] = traceback.format_exc()
            run["state"] = "FAILED"
            events = run["events"]
            assert isinstance(events, list)
            events.append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message=f"training failed: {exc}",
                    payload={"status": "failed", "traceback": run["traceback"]},
                )
            )

    async def status(self, external_job_id: str) -> JobStatus:
        run = self._runs.get(external_job_id)
        if run is None:
            return JobStatus.FAILED
        return {
            "RUNNING": JobStatus.RUNNING,
            "COMPLETED": JobStatus.COMPLETED,
            "CANCELLED": JobStatus.CANCELLED,
        }.get(str(run["state"]), JobStatus.FAILED)

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        run = self._runs.get(external_job_id)
        if run is None:
            return
        emitted = 0
        while True:
            events = run["events"]
            assert isinstance(events, list)
            while emitted < len(events):
                event = events[emitted]
                assert isinstance(event, TrainingEvent)
                yield event
                emitted += 1
            if run["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(0.2)

    async def cancel(self, external_job_id: str) -> bool:
        run = self._runs.get(external_job_id)
        if run is None:
            return False
        run["cancelled"] = True
        run["state"] = "CANCELLED"
        events = run["events"]
        assert isinstance(events, list)
        events.append(
            TrainingEvent(
                job_id=external_job_id.removeprefix("local-"),
                ts=datetime.now(UTC),
                message="training cancelled",
                payload={"status": "cancelled"},
            )
        )
        return True

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        run = self._runs.get(external_job_id)
        result = run.get("result") if run is not None else None
        if not isinstance(result, dict) or not isinstance(
            result.get("artifacts"), list
        ):
            return []
        refs: list[ArtifactRef] = []
        for item in result["artifacts"]:
            if not isinstance(item, dict) or not item.get("uri"):
                continue
            metadata = item.get("metadata", {})
            refs.append(
                ArtifactRef(
                    uri=str(item["uri"]),
                    kind=str(item.get("kind", "artifact")),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return refs
