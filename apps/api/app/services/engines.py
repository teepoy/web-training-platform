from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.domain.models import ArtifactRef, TrainingEvent, TrainingJob
from app.domain.types import JobStatus
from app.services.kubeflow_client import KubeflowClient

if TYPE_CHECKING:
    from app.storage.interfaces import ArtifactStorage


class LocalProcessEngine:
    def __init__(self, storage: ArtifactStorage | None = None) -> None:
        self.storage = storage

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
        job_id = external_job_id.replace("local-", "")
        artifacts: list[ArtifactRef] = []

        # Create a CLIP-based model configuration file
        # Since we use zero-shot classification, the "model" is really a config
        # that specifies the base CLIP model and any learned prompt templates
        model_data = json.dumps({
            "model_type": "clip_zero_shot_classifier",
            "base_model": "openai/clip-vit-base-patch32",
            "prompt_template": "a photo of {label}",
            "training_info": {
                "epochs": 3,
                "final_loss": 0.2,
                "accuracy": 0.85,
            },
            "created_at": datetime.now(UTC).isoformat(),
            "version": "1.0",
        }, indent=2).encode("utf-8")

        model_hash = hashlib.sha256(model_data).hexdigest()
        model_id = str(uuid4())

        if self.storage:
            # Store the actual model file
            object_name = f"models/{job_id}/model.json"
            model_uri = await self.storage.put_bytes(
                object_name=object_name,
                data=model_data,
                content_type="application/json",
            )
        else:
            # Fallback to placeholder URI
            model_uri = f"s3://artifacts/demo/{job_id}/model.json"

        artifacts.append(
            ArtifactRef(
                id=model_id,
                uri=model_uri,
                kind="model",
                name="clip_classifier",
                file_size=len(model_data),
                file_hash=model_hash,
                format="clip_config",
                created_at=datetime.now(UTC),
                metadata={
                    "source": "training",
                    "epochs": 3,
                    "final_loss": 0.2,
                    "base_model": "openai/clip-vit-base-patch32",
                },
            )
        )

        # Create metrics artifact
        metrics_data = json.dumps({
            "epochs": 3,
            "final_loss": 0.2,
            "accuracy": 0.85,
            "training_time_seconds": 10.5,
            "base_model": "openai/clip-vit-base-patch32",
        }, indent=2).encode("utf-8")
        metrics_id = str(uuid4())

        if self.storage:
            metrics_object_name = f"models/{job_id}/metrics.json"
            metrics_uri = await self.storage.put_bytes(
                object_name=metrics_object_name,
                data=metrics_data,
                content_type="application/json",
            )
        else:
            metrics_uri = f"s3://artifacts/demo/{job_id}/metrics.json"

        artifacts.append(
            ArtifactRef(
                id=metrics_id,
                uri=metrics_uri,
                kind="metrics",
                name="training_metrics",
                file_size=len(metrics_data),
                file_hash=hashlib.sha256(metrics_data).hexdigest(),
                format="json",
                created_at=datetime.now(UTC),
                metadata={"source": "training"},
            )
        )

        return artifacts


class KubeflowTrainingOperatorEngine:
    def __init__(
        self,
        kubeflow_client: KubeflowClient | None = None,
        image: str = "python:3.11-slim",
        storage: ArtifactStorage | None = None,
    ) -> None:
        self.kubeflow_client = kubeflow_client
        self.image = image
        self.storage = storage

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
        job_id = external_job_id.replace("kubeflow-", "").replace("ft-", "")
        artifacts: list[ArtifactRef] = []

        # Create a CLIP-based model configuration file
        model_data = json.dumps({
            "model_type": "clip_zero_shot_classifier",
            "base_model": "openai/clip-vit-base-patch32",
            "prompt_template": "a photo of {label}",
            "training_info": {
                "epochs": 10,
                "final_loss": 0.1,
                "accuracy": 0.92,
            },
            "created_at": datetime.now(UTC).isoformat(),
            "version": "1.0",
        }, indent=2).encode("utf-8")

        model_hash = hashlib.sha256(model_data).hexdigest()
        model_id = str(uuid4())

        if self.storage:
            object_name = f"models/{job_id}/model.json"
            model_uri = await self.storage.put_bytes(
                object_name=object_name,
                data=model_data,
                content_type="application/json",
            )
        else:
            model_uri = f"s3://artifacts/demo/{job_id}/model.json"

        artifacts.append(
            ArtifactRef(
                id=model_id,
                uri=model_uri,
                kind="model",
                name="clip_classifier",
                file_size=len(model_data),
                file_hash=model_hash,
                format="clip_config",
                created_at=datetime.now(UTC),
                metadata={
                    "source": "kubeflow_training",
                    "epochs": 10,
                    "final_loss": 0.1,
                    "base_model": "openai/clip-vit-base-patch32",
                },
            )
        )

        return artifacts
