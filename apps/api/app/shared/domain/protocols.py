from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.shared.api.schemas import ArtifactRef, TrainingEvent, TrainingJob


class ArtifactStorage(Protocol):
    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store bytes and return the URI."""
        ...

    async def get_bytes(self, uri: str) -> bytes:
        """Retrieve bytes from the given URI."""
        ...

    async def delete(self, uri: str) -> None:
        """Delete the object at the given URI."""
        ...


class TrainingExecutionEngine(Protocol):
    async def submit(self, job: TrainingJob) -> str:
        """Submit a training job and return an external execution ID."""
        ...

    def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        """Stream execution events until the job reaches a terminal state."""
        ...

    async def collect_artifacts(self, external_job_id: str) -> list[ArtifactRef]:
        """Collect artifact references emitted by the execution backend."""
        ...

    async def cancel(self, external_job_id: str) -> bool:
        """Cancel the external execution if possible."""
        ...


class NotificationSink(Protocol):
    def notify_job_update(self, event: TrainingEvent) -> None:
        """Notify listeners about a non-terminal job update."""
        ...

    def notify_job_terminal(self, event: TrainingEvent) -> None:
        """Notify listeners that a job reached a terminal state."""
        ...

    def notify_user_left_and_complete(self, event: TrainingEvent) -> None:
        """Notify listeners when a job completes after the user has left."""
        ...


class LabelStudioClient(Protocol):
    async def create_project(
        self, name: str, label_config: str
    ) -> dict[str, object]: ...

    async def update_project(
        self, project_id: int, *, label_config: str | None = None
    ) -> dict[str, object]: ...

    async def delete_project(self, project_id: int) -> None: ...

    async def create_task(
        self, project_id: int, data: dict[str, object]
    ) -> dict[str, object]: ...

    async def import_tasks(
        self,
        project_id: int,
        tasks: list[dict[str, object]],
        return_task_ids: bool = True,
    ) -> dict[str, object]: ...

    async def create_annotation(
        self, task_id: int, result: list[dict[str, object]]
    ) -> dict[str, object]: ...

    async def create_prediction(
        self,
        task_id: int,
        result: list[dict[str, object]],
        model_version: str | None = None,
        score: float | None = None,
    ) -> dict[str, object]: ...

    @staticmethod
    def generate_image_classification_config(label_space: list[str]) -> str: ...

    @staticmethod
    def generate_vqa_config() -> str: ...


class LlmClient(Protocol):
    async def answer_vqa(
        self,
        *,
        image_bytes: bytes,
        question: str,
        system_prompt: str,
    ) -> str: ...


class PrefectClient(Protocol):
    async def ensure_work_pool(
        self,
        name: str,
        type: str,
        concurrency_limit: int,
    ) -> dict[str, Any]: ...

    async def get_work_pool(self, name: str) -> dict[str, Any]: ...

    async def list_work_queues(
        self, work_pool_name: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def resolve_deployment_id(self, deployment_name: str) -> str | None: ...

    async def get_deployment(self, deployment_id: str) -> dict[str, Any]: ...

    async def get_work_queue_by_name(
        self,
        name: str,
        work_pool_name: str | None = None,
    ) -> dict[str, Any] | None: ...

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...

    async def get_flow_run(self, flow_run_id: str) -> dict[str, Any]: ...

    async def get_flow_run_logs(
        self,
        flow_run_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...

    async def list_task_runs(
        self,
        flow_run_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...

    async def set_flow_run_state(
        self,
        flow_run_id: str,
        state_type: str,
    ) -> dict[str, Any]: ...

    async def filter_flow_runs(
        self,
        work_pool_name: str | None = None,
        work_queue_name: str | None = None,
        deployment_id: str | None = None,
        state_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...


class EmbeddingClient(Protocol):
    async def embed_image(
        self,
        image_bytes: bytes,
        model_name: str = "openai/clip-vit-base-patch32",
    ) -> list[float]: ...

    async def health(self) -> bool: ...


class InferenceWorker(Protocol):
    async def predict_batch(
        self,
        *,
        model_id: str,
        model_uri: str,
        model_format: str | None,
        model_metadata: dict[str, Any],
        model_bytes: bytes,
        target: str,
        label_space: list[str],
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    async def embed_batch(
        self,
        *,
        model_name: str,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


class GpuWorker(Protocol):
    async def submit_train(
        self,
        *,
        platform_job_id: str,
        preset_id: str,
        dataset_id: str,
        model_id: str = "",
        hyperparameters: dict[str, Any] | None = None,
        artifact_prefix: str = "",
    ) -> dict[str, Any]: ...

    async def get_train_status(self, job_id: str) -> dict[str, Any]: ...

    async def predict_batch(
        self,
        *,
        model_id: str,
        model_uri: str,
        model_format: str | None,
        model_metadata: dict[str, Any],
        model_bytes: bytes,
        target: str,
        label_space: list[str],
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    async def embed_batch(
        self,
        *,
        model_name: str,
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


class KubeflowClient(Protocol):
    async def submit_pytorch_job(
        self, job_name: str, image: str, command: list[str] | None = None
    ) -> str: ...

    async def get_job_phase(self, job_name: str) -> str: ...

    async def delete_job(self, job_name: str) -> bool: ...

    async def get_job_logs(self, job_name: str) -> str: ...
