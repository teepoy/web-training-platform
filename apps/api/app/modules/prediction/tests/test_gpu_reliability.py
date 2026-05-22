"""Focused reliability tests for GPU-worker delegated training.

These tests keep first-version reliability semantics deterministic without a
real GPU worker: duplicate submissions are idempotent, GPU-side failures become
terminal platform failures, cancellation reaches the worker-facing engine, and
Prefect submit retries reuse the same platform job id.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.api.schemas import TrainingEvent, TrainingJob
from app.shared.api.schemas import JobStatus
from app.shared.infrastructure.workers.gpu_worker import (
    GpuWorkerClient,
    GpuWorkerClientError,
    GpuWorkerUnavailableError,
)
from app.modules.training.application.services.orchestrator import TrainingOrchestrator
from app.modules.training.infrastructure.engines.prefect_engine import PrefectWorkPoolEngine

BASE_URL = "http://gpu-worker:9999"


def _response(status: int, body: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.is_success = 200 <= status < 300
    response.text = text
    response.json = MagicMock(return_value=body or {})
    if status >= 400:
        response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status}",
                request=MagicMock(),
                response=response,
            )
        )
    else:
        response.raise_for_status = MagicMock()
    return response


def _mock_http(*responses: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _stream(*events: TrainingEvent) -> AsyncIterator[TrainingEvent]:
    for event in events:
        yield event


class _GpuTrainingEngine:
    """Small engine adapter that exercises GPU submit/poll/cancel semantics."""

    def __init__(self, gpu_worker: MagicMock) -> None:
        self.gpu_worker = gpu_worker
        self.platform_by_external: dict[str, str] = {}

    async def submit(self, job: TrainingJob) -> str:
        result = await self.gpu_worker.submit_train(
            platform_job_id=job.id,
            preset_id=job.preset_id,
            dataset_id=job.dataset_id,
        )
        gpu_job_id = str(result["job_id"])
        self.platform_by_external[gpu_job_id] = job.id
        return gpu_job_id

    async def stream_events(self, external_job_id: str) -> AsyncIterator[TrainingEvent]:
        job_id = self.platform_by_external[external_job_id]
        try:
            status = await self.gpu_worker.get_train_status(external_job_id)
        except GpuWorkerClientError as exc:
            yield TrainingEvent(
                job_id=job_id,
                message="gpu worker error",
                payload={
                    "status": "failed",
                    "gpu_job_id": external_job_id,
                    "gpu_worker_error": str(exc),
                },
            )
            return

        current_status = str(status.get("status", ""))
        if current_status == "completed":
            yield TrainingEvent(
                job_id=job_id,
                message="training completed",
                payload={"status": "completed", "gpu_job_id": external_job_id},
            )
        elif current_status == "cancelled":
            yield TrainingEvent(
                job_id=job_id,
                message="training cancelled",
                payload={"status": "cancelled", "gpu_job_id": external_job_id},
            )
        else:
            error = status.get("error") or f"GPU training {current_status or 'failed'}"
            yield TrainingEvent(
                job_id=job_id,
                message="gpu worker error",
                payload={
                    "status": "failed",
                    "gpu_job_id": external_job_id,
                    "gpu_worker_error": error,
                },
            )

    async def cancel(self, external_job_id: str) -> bool:
        await self.gpu_worker.cancel_train(external_job_id)
        return True

    async def collect_artifacts(self, external_job_id: str) -> list:
        return []


def _orchestrator_with(engine: object, repository: AsyncMock) -> TrainingOrchestrator:
    repository.did_user_leave.return_value = False
    return TrainingOrchestrator(
        engine=engine,
        notification_sink=MagicMock(),
        repository=repository,
        artifact_service=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_duplicate_submit_is_idempotent() -> None:
    first = {"job_id": "gpu-existing", "status": "accepted", "position": 0}
    duplicate = {
        "job_id": "gpu-existing",
        "status": "already_submitted",
        "detail": "platform job already submitted",
    }
    http = _mock_http(_response(202, first), _response(409, duplicate))

    with patch("httpx.AsyncClient", return_value=http):
        client = GpuWorkerClient(base_url=BASE_URL)
        first_result = await client.submit_train(
            platform_job_id="platform-job-dup",
            preset_id="resnet50-cls-v1",
            dataset_id="dataset-1",
        )
        duplicate_result = await client.submit_train(
            platform_job_id="platform-job-dup",
            preset_id="resnet50-cls-v1",
            dataset_id="dataset-1",
        )

    assert first_result["job_id"] == "gpu-existing"
    assert duplicate_result["job_id"] == "gpu-existing"
    assert duplicate_result["status"] == "already_submitted"
    assert http.post.await_count == 2
    submitted_platform_ids = [call.kwargs["json"]["platform_job_id"] for call in http.post.await_args_list]
    assert submitted_platform_ids == ["platform-job-dup", "platform-job-dup"]


@pytest.mark.asyncio
async def test_unavailable_gpu_worker_marks_job_failed() -> None:
    failed_event = TrainingEvent(
        job_id="platform-job-unavailable",
        message="gpu worker error",
        payload={
            "status": "failed",
            "gpu_worker_error": "GPU worker unreachable",
        },
    )
    engine = AsyncMock()
    engine.submit.return_value = "prefect-run-1"
    engine.stream_events = MagicMock(return_value=_stream(failed_event))
    repository = AsyncMock()
    job = TrainingJob(
        id="platform-job-unavailable",
        dataset_id="dataset-1",
        preset_id="resnet50-cls-v1",
        created_by="test",
    )
    orchestrator = _orchestrator_with(engine, repository)

    with patch("app.modules.training.application.services.orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        await orchestrator.start_job(job)

    await asyncio.wait_for(orchestrator._run_job(job.id, "prefect-run-1"), timeout=1)

    repository.update_job_status.assert_any_await(job.id, JobStatus.FAILED)
    repository.add_event.assert_any_await(failed_event)
    persisted = [call.args[0] for call in repository.add_event.await_args_list]
    assert any(event.payload.get("gpu_worker_error") == "GPU worker unreachable" for event in persisted)


@pytest.mark.asyncio
async def test_cancellation_propagates_to_gpu_worker() -> None:
    gpu_worker = MagicMock()
    gpu_worker.submit_train = AsyncMock(return_value={"job_id": "gpu-cancel-1", "status": "accepted"})
    gpu_worker.cancel_train = AsyncMock(return_value={"job_id": "gpu-cancel-1", "status": "cancelled"})
    engine = _GpuTrainingEngine(gpu_worker)
    repository = AsyncMock()
    repository.get_job_external_id.return_value = "gpu-cancel-1"
    job = TrainingJob(
        id="platform-job-cancel",
        dataset_id="dataset-1",
        preset_id="resnet50-cls-v1",
        created_by="test",
    )
    orchestrator = _orchestrator_with(engine, repository)

    with patch("app.modules.training.application.services.orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        await orchestrator.start_job(job)
    cancelled = await asyncio.wait_for(orchestrator.cancel_job(job.id), timeout=1)

    assert cancelled is True
    gpu_worker.cancel_train.assert_awaited_once_with("gpu-cancel-1")
    repository.update_job_status.assert_any_await(job.id, JobStatus.CANCELLED)


@pytest.mark.asyncio
async def test_gpu_worker_crash_loses_job() -> None:
    gpu_worker = MagicMock()
    gpu_worker.submit_train = AsyncMock(return_value={"job_id": "gpu-lost-1", "status": "accepted"})
    gpu_worker.get_train_status = AsyncMock(
        side_effect=GpuWorkerUnavailableError("GPU worker unreachable during status check")
    )
    engine = _GpuTrainingEngine(gpu_worker)
    repository = AsyncMock()
    job = TrainingJob(
        id="platform-job-lost",
        dataset_id="dataset-1",
        preset_id="resnet50-cls-v1",
        created_by="test",
    )
    orchestrator = _orchestrator_with(engine, repository)

    with patch("app.modules.training.application.services.orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        await orchestrator.start_job(job)
    await asyncio.wait_for(orchestrator._run_job(job.id, "gpu-lost-1"), timeout=1)

    repository.update_job_status.assert_any_await(job.id, JobStatus.FAILED)
    terminal_event = repository.add_event.await_args_list[-1].args[0]
    assert terminal_event.payload["status"] == "failed"
    assert terminal_event.payload["gpu_job_id"] == "gpu-lost-1"
    assert "unreachable" in str(terminal_event.payload["gpu_worker_error"])


@pytest.mark.asyncio
async def test_gpu_oom_failure_marks_job_failed() -> None:
    gpu_worker = MagicMock()
    gpu_worker.submit_train = AsyncMock(return_value={"job_id": "gpu-oom-1", "status": "accepted"})
    gpu_worker.get_train_status = AsyncMock(
        return_value={"job_id": "gpu-oom-1", "status": "failed", "error": "CUDA out of memory"}
    )
    engine = _GpuTrainingEngine(gpu_worker)
    repository = AsyncMock()
    job = TrainingJob(
        id="platform-job-oom",
        dataset_id="dataset-1",
        preset_id="resnet50-cls-v1",
        created_by="test",
    )
    orchestrator = _orchestrator_with(engine, repository)

    with patch("app.modules.training.application.services.orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        await orchestrator.start_job(job)
    await asyncio.wait_for(orchestrator._run_job(job.id, "gpu-oom-1"), timeout=1)

    repository.update_job_status.assert_any_await(job.id, JobStatus.FAILED)
    terminal_event = repository.add_event.await_args_list[-1].args[0]
    assert terminal_event.payload == {
        "status": "failed",
        "gpu_job_id": "gpu-oom-1",
        "gpu_worker_error": "CUDA out of memory",
    }


@pytest.mark.asyncio
async def test_idempotency_across_retries() -> None:
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "deployment-1"
    client.create_flow_run_from_deployment.side_effect = [
        {"id": "prefect-run-existing"},
        {"id": "prefect-run-existing"},
    ]
    engine = PrefectWorkPoolEngine(
        prefect_client=client,
        work_pool_name="gpu-pool",
        work_pool_type="process",
        flow_name="train-job",
    )
    job = TrainingJob(
        id="platform-job-retry",
        dataset_id="dataset-1",
        preset_id="resnet50-cls-v1",
        created_by="test",
    )

    first_run_id = await engine.submit(job)
    retry_run_id = await engine.submit(job)

    assert first_run_id == "prefect-run-existing"
    assert retry_run_id == "prefect-run-existing"
    assert client.create_flow_run_from_deployment.await_count == 2
    submit_kwargs = [call.kwargs for call in client.create_flow_run_from_deployment.await_args_list]
    assert [kwargs["idempotency_key"] for kwargs in submit_kwargs] == [job.id, job.id]
    assert [kwargs["parameters"]["job_id"] for kwargs in submit_kwargs] == [job.id, job.id]
