from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.domain.models import ArtifactRef, TrainingEvent, TrainingJob
from app.domain.types import JobStatus
from app.services.kubeflow_client import KubeflowClient


class LocalProcessEngine:
    async def submit(self, job: TrainingJob) -> str:
        return f"local-{job.id}"

    async def status(self, external_job_id: str) -> JobStatus:
        return JobStatus.RUNNING

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        for epoch in range(1, 4):
            await asyncio.sleep(0.05)
            yield TrainingEvent(
                job_id=external_job_id.replace("local-", ""),
                ts=datetime.now(UTC),
                message=f"epoch {epoch} complete",
                payload={"epoch": epoch, "loss": round(1.0 / epoch, 4)},
            )
        yield TrainingEvent(
            job_id=external_job_id.replace("local-", ""),
            ts=datetime.now(UTC),
            message="training completed",
            payload={"status": "completed"},
        )

    async def cancel(self, external_job_id: str) -> bool:
        return True

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        base = external_job_id.replace("local-", "")
        return [
            ArtifactRef(uri=f"s3://artifacts/demo/{base}/model", kind="model"),
            ArtifactRef(uri=f"s3://artifacts/demo/{base}/metrics.json", kind="metrics"),
        ]


class KubeflowTrainingOperatorEngine:
    def __init__(self, kubeflow_client: KubeflowClient | None = None, image: str = "python:3.11-slim") -> None:
        self.kubeflow_client = kubeflow_client
        self.image = image

    async def submit(self, job: TrainingJob) -> str:
        name = f"ft-{job.id}"[:63]
        if self.kubeflow_client is None:
            return f"kubeflow-{job.id}"
        try:
            return await self.kubeflow_client.submit_pytorch_job(job_name=name, image=self.image)
        except Exception:
            return f"kubeflow-{job.id}"

    async def status(self, external_job_id: str) -> JobStatus:
        if self.kubeflow_client is not None:
            try:
                phase = await self.kubeflow_client.get_job_phase(external_job_id)
                if phase in {"Succeeded"}:
                    return JobStatus.COMPLETED
                if phase in {"Failed"}:
                    return JobStatus.FAILED
            except Exception:
                return JobStatus.RUNNING
        return JobStatus.RUNNING

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        if external_job_id.startswith("kubeflow-"):
            job_id = external_job_id.replace("kubeflow-", "")
            yield TrainingEvent(job_id=job_id, message="kubeflow job accepted", payload={"phase": "accepted"})
            yield TrainingEvent(job_id=job_id, message="kubeflow worker pod running", payload={"phase": "running"})
            yield TrainingEvent(job_id=job_id, message="training completed", payload={"status": "completed"})
            return

        job_id = external_job_id.replace("ft-", "")
        yield TrainingEvent(job_id=job_id, message="kubeflow job accepted", payload={"phase": "accepted"})
        while True:
            status = await self.status(external_job_id)
            if status == JobStatus.COMPLETED:
                yield TrainingEvent(job_id=job_id, message="training completed", payload={"status": "completed"})
                break
            if status == JobStatus.FAILED:
                yield TrainingEvent(job_id=job_id, message="training failed", payload={"status": "failed"})
                break
            yield TrainingEvent(job_id=job_id, message="kubeflow worker running", payload={"phase": "running"})
            await asyncio.sleep(2)

    async def cancel(self, external_job_id: str) -> bool:
        if self.kubeflow_client is not None and not external_job_id.startswith("kubeflow-"):
            return await self.kubeflow_client.delete_job(external_job_id)
        return True

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        base = external_job_id.replace("kubeflow-", "")
        return [
            ArtifactRef(uri=f"s3://artifacts/demo/{base}/model", kind="model"),
            ArtifactRef(uri=f"s3://artifacts/demo/{base}/events", kind="events"),
        ]
