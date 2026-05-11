from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.models import PredictionJob
from app.domain.models import PredictionEvent
from app.domain.types import JobStatus
from app.services.prediction_orchestrator import PredictionOrchestrator


@pytest.mark.asyncio
async def test_start_job_uses_batch_prediction_deployment() -> None:
    prefect_client = AsyncMock()
    prefect_client.resolve_deployment_id.return_value = "deploy-predict-1"
    prefect_client.create_flow_run_from_deployment.return_value = {"id": "flow-run-1"}

    repository = AsyncMock()
    job = PredictionJob(
        dataset_id="dataset-1",
        model_id="model-1",
        created_by="user-1",
        org_id="org-1",
        status=JobStatus.QUEUED,
    )
    repository.get_prediction_job.return_value = job.model_copy(update={"status": JobStatus.RUNNING, "external_job_id": "flow-run-1"})

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with patch("app.services.prediction_orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        started = await orchestrator.start_job(job)

    prefect_client.resolve_deployment_id.assert_awaited_once_with("predict-job-batch-deployment")
    prefect_client.create_flow_run_from_deployment.assert_awaited_once()
    repository.create_prediction_job.assert_awaited_once_with(job)
    repository.set_prediction_job_external_id.assert_awaited_once_with(job.id, "flow-run-1")
    repository.update_prediction_job_status.assert_awaited_once_with(job.id, JobStatus.RUNNING)
    assert started.external_job_id == "flow-run-1"


@pytest.mark.asyncio
async def test_start_job_raises_when_batch_prediction_deployment_missing() -> None:
    prefect_client = AsyncMock()
    prefect_client.resolve_deployment_id.return_value = None
    repository = AsyncMock()
    job = PredictionJob(
        dataset_id="dataset-1",
        model_id="model-1",
        created_by="user-1",
        org_id="org-1",
    )

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with pytest.raises(ValueError, match="Prediction deployment is not registered"):
        await orchestrator.start_job(job)

    prefect_client.resolve_deployment_id.assert_awaited_once_with("predict-job-batch-deployment")
    prefect_client.create_flow_run_from_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_start_embedding_job_uses_embed_batch_deployment() -> None:
    prefect_client = AsyncMock()
    prefect_client.resolve_deployment_id.return_value = "deploy-embed-1"
    prefect_client.create_flow_run_from_deployment.return_value = {"id": "flow-run-embed-1"}

    repository = AsyncMock()
    job = PredictionJob(
        dataset_id="dataset-1",
        model_id="embedding-worker",
        created_by="user-1",
        org_id="org-1",
        target="embedding",
        status=JobStatus.QUEUED,
    )
    repository.get_prediction_job.return_value = job.model_copy(update={"status": JobStatus.RUNNING, "external_job_id": "flow-run-embed-1"})

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with patch("app.services.prediction_orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()):
        started = await orchestrator.start_job(job)

    prefect_client.resolve_deployment_id.assert_awaited_once_with("embed-job-batch-deployment")
    prefect_client.create_flow_run_from_deployment.assert_awaited_once()
    assert started.external_job_id == "flow-run-embed-1"


@pytest.mark.asyncio
async def test_poll_run_marks_completed_and_persists_summary() -> None:
    prefect_client = AsyncMock()
    prefect_client.get_flow_run.side_effect = [
        {"state": {"type": "RUNNING"}},
        {"state": {"type": "COMPLETED"}},
        {"state": {"type": "COMPLETED", "data": {"processed": 2, "successful": 2, "failed": 0}}},
    ]
    prefect_client.get_flow_run_logs.side_effect = [[], [{"message": "chunk done", "level": 20}]]
    repository = AsyncMock()

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with patch("app.services.prediction_orchestrator.asyncio.sleep", new=AsyncMock()):
        await orchestrator._poll_run("job-1", "flow-run-1")

    repository.update_prediction_job_status.assert_awaited_once_with(
        "job-1",
        JobStatus.COMPLETED,
        summary={"processed": 2, "successful": 2, "failed": 0},
    )
    terminal_event = repository.add_prediction_event.await_args_list[-1].args[0]
    assert isinstance(terminal_event, PredictionEvent)
    assert terminal_event.message == "prediction completed"
    assert terminal_event.payload["status"] == "completed"


@pytest.mark.asyncio
async def test_poll_run_keeps_existing_summary_when_prefect_result_is_null() -> None:
    prefect_client = AsyncMock()
    prefect_client.get_flow_run.side_effect = [
        {"state": {"type": "COMPLETED"}},
        {"state": {"type": "COMPLETED", "data": None}},
    ]
    prefect_client.get_flow_run_logs.return_value = []
    repository = AsyncMock()
    repository.get_prediction_job.return_value = PredictionJob(
        id="job-keep-summary",
        dataset_id="dataset-1",
        model_id="model-1",
        created_by="user-1",
        org_id="org-1",
        status=JobStatus.RUNNING,
        summary={
            "total_samples": 2,
            "processed": 2,
            "successful": 2,
            "failed": 0,
            "predictions": [{"sample_id": "sample-1", "predicted_label": "cat"}],
        },
    )

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with patch("app.services.prediction_orchestrator.asyncio.sleep", new=AsyncMock()):
        await orchestrator._poll_run("job-keep-summary", "flow-run-keep-summary")

    repository.update_prediction_job_status.assert_awaited_once_with(
        "job-keep-summary",
        JobStatus.COMPLETED,
        summary={
            "total_samples": 2,
            "processed": 2,
            "successful": 2,
            "failed": 0,
            "predictions": [{"sample_id": "sample-1", "predicted_label": "cat"}],
        },
    )


@pytest.mark.asyncio
async def test_extract_summary_from_run_handles_prefect_models() -> None:
    class DummyStateData:
        def model_dump(self) -> dict:
            return {"processed": 2, "successful": 2, "failed": 0}

    summary = PredictionOrchestrator._extract_summary_from_run(
        {"state": {"type": "COMPLETED", "data": DummyStateData()}}
    )

    assert summary == {"processed": 2, "successful": 2, "failed": 0}


@pytest.mark.asyncio
async def test_poll_run_marks_crashed_flow_as_failed() -> None:
    prefect_client = AsyncMock()
    prefect_client.get_flow_run.side_effect = [
        {"state": {"type": "CRASHED"}},
        {"state": {"type": "CRASHED", "data": {"error": "flow load failed"}}},
    ]
    prefect_client.get_flow_run_logs.return_value = []
    repository = AsyncMock()

    orchestrator = PredictionOrchestrator(prefect_client=prefect_client, repository=repository)

    with patch("app.services.prediction_orchestrator.asyncio.sleep", new=AsyncMock()):
        await orchestrator._poll_run("job-2", "flow-run-2")

    repository.update_prediction_job_status.assert_awaited_once_with(
        "job-2",
        JobStatus.FAILED,
        summary={"error": "flow load failed"},
    )
    terminal_event = repository.add_prediction_event.await_args_list[-1].args[0]
    assert terminal_event.message == "prediction failed"
    assert terminal_event.payload["status"] == "failed"
