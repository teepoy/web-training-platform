from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.domain.models import ArtifactRef, TrainingEvent, TrainingJob
from app.domain.types import JobStatus
from app.runtime.training_runner import run_training_pipeline
from app.services.kubeflow_client import KubeflowClient


class LocalProcessEngine:
    def __init__(self, storage=None) -> None:
        self.storage = storage
        self._runs: dict[str, dict] = {}

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
            run["events"].append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="local training started",
                    payload={"phase": "running"},
                )
            )
            result = await run_training_pipeline(
                job_id=job.id,
                dataset_id=job.dataset_id,
                preset_id=job.preset_id,
                artifact_storage=self.storage,
            )
            run["result"] = result
            run["state"] = "COMPLETED"
            run["events"].append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="training completed",
                    payload={"status": "completed"},
                )
            )
        except Exception as exc:
            run["error"] = str(exc)
            run["state"] = "FAILED"
            run["events"].append(
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message=f"training failed: {exc}",
                    payload={"status": "failed"},
                )
            )

    async def status(self, external_job_id: str) -> JobStatus:
        run = self._runs.get(external_job_id)
        if run is None:
            return JobStatus.FAILED
        state = run["state"]
        if state == "RUNNING":
            return JobStatus.RUNNING
        if state == "COMPLETED":
            return JobStatus.COMPLETED
        if state == "CANCELLED":
            return JobStatus.CANCELLED
        return JobStatus.FAILED

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        run = self._runs.get(external_job_id)
        if run is None:
            return
        emitted = 0
        while True:
            events = run["events"]
            while emitted < len(events):
                yield events[emitted]
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
        run["events"].append(
            TrainingEvent(
                job_id=external_job_id.replace("local-", ""),
                ts=datetime.now(UTC),
                message="training cancelled",
                payload={"status": "cancelled"},
            )
        )
        return True

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        run = self._runs.get(external_job_id)
        if run is None:
            return []
        result = run.get("result")
        if not isinstance(result, dict):
            return []
        artifacts = result.get("artifacts", [])
        if not isinstance(artifacts, list):
            return []
        refs: list[ArtifactRef] = []
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri")
            if not uri:
                continue
            refs.append(
                ArtifactRef(
                    uri=str(uri),
                    kind=str(item.get("kind", "artifact")),
                    metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
                )
            )
        return refs


class KubeflowTrainingOperatorEngine:
    def __init__(
        self,
        kubeflow_client: KubeflowClient | None = None,
        image: str = "python:3.11-slim",
        storage=None,
    ) -> None:
        self.kubeflow_client = kubeflow_client
        self.image = image
        self.storage = storage

    async def submit(self, job: TrainingJob) -> str:
        name = f"ft-{job.id}"[:63]
        if self.kubeflow_client is None:
            raise RuntimeError("kubeflow client is not configured")
        return await self.kubeflow_client.submit_pytorch_job(
            job_name=name,
            image=self.image,
            command=[
                "uv",
                "run",
                "python",
                "-m",
                "app.runtime.training_runner",
                "--job-id",
                job.id,
                "--dataset-id",
                job.dataset_id,
                "--preset-id",
                job.preset_id,
            ],
        )

    async def status(self, external_job_id: str) -> JobStatus:
        if self.kubeflow_client is None:
            return JobStatus.FAILED
        phase = await self.kubeflow_client.get_job_phase(external_job_id)
        if phase in {"Succeeded"}:
            return JobStatus.COMPLETED
        if phase in {"Failed"}:
            return JobStatus.FAILED
        if phase in {"Stopped", "Terminated"}:
            return JobStatus.CANCELLED
        return JobStatus.RUNNING

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        job_id = external_job_id.replace("ft-", "")
        yield TrainingEvent(job_id=job_id, message="kubeflow job accepted", payload={"phase": "accepted"})
        last_phase = ""
        while True:
            phase = await self.kubeflow_client.get_job_phase(external_job_id) if self.kubeflow_client else "Failed"
            if phase != last_phase:
                yield TrainingEvent(job_id=job_id, message=f"kubeflow phase: {phase}", payload={"phase": phase})
                last_phase = phase
            if phase == "Succeeded":
                yield TrainingEvent(job_id=job_id, message="training completed", payload={"status": "completed"})
                break
            if phase == "Failed":
                yield TrainingEvent(job_id=job_id, message="training failed", payload={"status": "failed"})
                break
            if phase in {"Stopped", "Terminated"}:
                yield TrainingEvent(job_id=job_id, message="training cancelled", payload={"status": "cancelled"})
                break
            await asyncio.sleep(2)

    async def cancel(self, external_job_id: str) -> bool:
        if self.kubeflow_client is None:
            return False
        return await self.kubeflow_client.delete_job(external_job_id)

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        if self.kubeflow_client is None:
            return []
        try:
            logs = await self.kubeflow_client.get_job_logs(external_job_id)
            last_line = logs.strip().splitlines()[-1] if logs.strip() else ""
            payload = json.loads(last_line) if last_line.startswith("{") else {}
            artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
            refs: list[ArtifactRef] = []
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                uri = item.get("uri")
                if not uri:
                    continue
                refs.append(
                    ArtifactRef(
                        uri=str(uri),
                        kind=str(item.get("kind", "artifact")),
                        metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
                    )
                )
            return refs
        except Exception:
            return []
