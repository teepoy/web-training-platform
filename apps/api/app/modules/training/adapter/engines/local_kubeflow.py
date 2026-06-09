from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.shared.api.schemas import ArtifactRef, TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.core.prefect_runner import submit_flow_run_and_wait
from app.shared.domain.protocols import KubeflowClient


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
            from app.modules.training.flows.train_job import run_training_pipeline

            result = await run_training_pipeline(
                job_id=job.id,
                dataset_id=job.dataset_id,
                trainer_id=job.trainer_id,
                artifact_storage=self.storage,
            )
            run["result"] = result
            run["state"] = "COMPLETED"

            metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
            if isinstance(metrics, dict) and metrics:
                metric_payload: dict[str, object] = dict(metrics)
                run["events"].append(
                    TrainingEvent(
                        job_id=job.id,
                        ts=datetime.now(UTC),
                        level="metric",
                        message="training metrics",
                        payload=metric_payload,
                    )
                )
                epochs = metrics.get("epochs", 0)
                epoch_losses = (
                    metrics.get("epoch_losses", [])
                    if isinstance(metrics.get("epoch_losses"), list)
                    else []
                )
                for ep in range(1, int(epochs) + 1):
                    ep_payload: dict[str, object] = {"epoch": ep}
                    if ep - 1 < len(epoch_losses):
                        ep_payload["val/loss"] = float(epoch_losses[ep - 1])
                    run["events"].append(
                        TrainingEvent(
                            job_id=job.id,
                            ts=datetime.now(UTC),
                            level="epoch",
                            message=f"epoch {ep} completed",
                            payload=ep_payload,
                        )
                    )

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
                    metadata=item.get("metadata", {})
                    if isinstance(item.get("metadata", {}), dict)
                    else {},
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
        self._runs: dict[str, dict] = {}

    async def submit(self, job: TrainingJob) -> str:
        external_id = f"ft-{job.id}"[:63]
        self._runs[external_id] = {
            "state": "RUNNING",
            "result": None,
            "error": None,
            "cancelled": False,
            "events": [
                TrainingEvent(
                    job_id=job.id,
                    ts=datetime.now(UTC),
                    message="kubeflow training accepted (prefect flow)",
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
                    message="kubeflow training started (prefect flow)",
                    payload={"phase": "running"},
                )
            )
            result = await submit_flow_run_and_wait(
                deployment_name="training-train-job",
                parameters={
                    "job_id": job.id,
                    "dataset_id": job.dataset_id,
                    "trainer_id": job.trainer_id,
                    "created_by": job.created_by,
                },
                timeout_seconds=3600.0,
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
            await asyncio.sleep(2)

    async def cancel(self, external_job_id: str) -> bool:
        run = self._runs.get(external_job_id)
        if run is None:
            return False
        run["cancelled"] = True
        run["state"] = "CANCELLED"
        run["events"].append(
            TrainingEvent(
                job_id=external_job_id.replace("ft-", ""),
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
                    metadata=item.get("metadata", {})
                    if isinstance(item.get("metadata", {}), dict)
                    else {},
                )
            )
        return refs
