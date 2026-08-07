from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.shared.api.schemas import ArtifactRef, JobStatus, TrainingEvent, TrainingJob


class ArtifactStorage(Protocol):
    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store bytes and return the URI."""
        ...

    async def put_file(
        self,
        object_name: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store a local file without first materializing it as one bytes object."""
        ...

    async def get_bytes(self, uri: str) -> bytes:
        """Retrieve bytes from the given URI."""
        ...

    async def get_file(self, uri: str, destination: str) -> None:
        """Stream an object into a local file."""
        ...

    async def delete(self, uri: str) -> None:
        """Delete the object at the given URI."""
        ...

    async def list_prefix(self, prefix: str) -> list[str]:
        """Return URIs of all objects whose key starts with the given prefix."""
        ...


class TrainingExecutionEngine(Protocol):
    async def submit(self, job: TrainingJob) -> str:
        """Submit a training job and return an external execution ID."""
        ...

    async def status(self, external_job_id: str) -> JobStatus:
        """Return the current execution status."""
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


class PrefectClient(Protocol):
    async def close(self) -> None: ...

    async def ensure_work_pool(
        self,
        name: str,
        type: str,
        concurrency_limit: int | None = None,
    ) -> dict[str, Any]: ...

    async def ensure_deployment(
        self,
        deployment_name: str,
        flow_name: str,
        work_pool_name: str,
        *,
        entrypoint: str | None = None,
        path: str | None = None,
        parameters: dict[str, object] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]: ...

    async def resolve_existing_flow_id(self, flow_name: str) -> str | None: ...

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
        offset: int = 0,
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


class KubeflowClient(Protocol):
    async def submit_pytorch_job(
        self, job_name: str, image: str, command: list[str] | None = None
    ) -> str: ...

    async def get_job_phase(self, job_name: str) -> str: ...

    async def delete_job(self, job_name: str) -> bool: ...

    async def get_job_logs(self, job_name: str) -> str: ...
