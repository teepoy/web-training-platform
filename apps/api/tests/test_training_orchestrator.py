from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.domain.models import ArtifactRef, TrainingEvent, TrainingJob
from app.domain.types import JobStatus
from app.services.orchestrator import TrainingOrchestrator


async def _event_stream(*events: TrainingEvent):
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_start_job_persists_running_state_and_schedules_background_execution() -> None:
    engine = AsyncMock()
    engine.submit.return_value = "external-run-1"
    notification_sink = Mock()
    repository = AsyncMock()
    artifact_service = AsyncMock()
    job = TrainingJob(dataset_id="dataset-1", preset_id="preset-1", created_by="user-1")

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    with patch("app.services.orchestrator.asyncio.create_task", side_effect=lambda coro: coro.close()) as create_task:
        started = await orchestrator.start_job(job)

    assert started.status == JobStatus.RUNNING
    repository.create_job.assert_awaited_once_with(job)
    engine.submit.assert_awaited_once_with(job)
    repository.set_job_external_id.assert_awaited_once_with(job.id, "external-run-1")
    repository.update_job_status.assert_awaited_once_with(job.id, JobStatus.RUNNING)
    repository.add_event.assert_awaited_once()
    queued_event = repository.add_event.await_args.args[0]
    assert queued_event.job_id == job.id
    assert queued_event.message == "job started"
    assert queued_event.payload == {"external_id": "external-run-1"}
    notification_sink.notify_job_update.assert_called_once_with(queued_event)
    create_task.assert_called_once()


@pytest.mark.asyncio
async def test_run_job_marks_completed_and_persists_only_new_artifacts() -> None:
    existing_artifact = ArtifactRef(id="artifact-existing", uri="s3://bucket/existing.bin", kind="model")
    new_artifact = ArtifactRef(id="artifact-new", uri="s3://bucket/new.bin", kind="metrics")
    running_event = TrainingEvent(job_id="job-1", message="prefect state: RUNNING", payload={"prefect_state": "RUNNING"})
    completed_event = TrainingEvent(job_id="job-1", message="training completed", payload={"status": "completed"})

    engine = Mock()
    engine.stream_events = Mock(side_effect=lambda external_id: _event_stream(running_event, completed_event))
    engine.collect_artifacts = AsyncMock(return_value=[existing_artifact, new_artifact])
    notification_sink = Mock()
    repository = AsyncMock()
    repository.get_job.return_value = TrainingJob(
        id="job-1",
        dataset_id="dataset-1",
        preset_id="preset-1",
        created_by="user-1",
        artifact_refs=[existing_artifact],
    )
    repository.did_user_leave.return_value = False
    artifact_service = AsyncMock()

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    await orchestrator._run_job("job-1", "external-run-1")

    repository.add_event.assert_any_await(running_event)
    repository.add_event.assert_any_await(completed_event)
    repository.update_job_status.assert_awaited_once_with("job-1", JobStatus.COMPLETED)
    artifact_service.persist_job_artifacts.assert_awaited_once_with("job-1", [new_artifact])
    notification_sink.notify_job_terminal.assert_called_once_with(completed_event)
    notification_sink.notify_user_left_and_complete.assert_not_called()


@pytest.mark.asyncio
async def test_run_job_fails_when_completed_without_any_artifacts() -> None:
    completed_event = TrainingEvent(job_id="job-2", message="training completed", payload={"status": "completed"})

    engine = Mock()
    engine.stream_events = Mock(side_effect=lambda external_id: _event_stream(completed_event))
    engine.collect_artifacts = AsyncMock(return_value=[])
    notification_sink = Mock()
    repository = AsyncMock()
    repository.get_job.return_value = TrainingJob(
        id="job-2",
        dataset_id="dataset-2",
        preset_id="preset-2",
        created_by="user-2",
    )
    repository.did_user_leave.return_value = False
    artifact_service = AsyncMock()

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    await orchestrator._run_job("job-2", "external-run-2")

    assert repository.update_job_status.await_args_list == [(("job-2", JobStatus.FAILED),)]
    failure_event = repository.add_event.await_args_list[-1].args[0]
    assert failure_event.message == "training failed: execution completed without artifacts"
    assert failure_event.payload == {"status": "failed", "reason": "missing_artifacts"}
    notification_sink.notify_job_terminal.assert_called_once_with(failure_event)
    artifact_service.persist_job_artifacts.assert_not_called()


@pytest.mark.asyncio
async def test_run_job_notifies_user_left_on_terminal_failure() -> None:
    failed_event = TrainingEvent(job_id="job-3", message="training failed", payload={"status": "failed"})

    engine = Mock()
    engine.stream_events = Mock(side_effect=lambda external_id: _event_stream(failed_event))
    notification_sink = Mock()
    repository = AsyncMock()
    repository.did_user_leave.return_value = True
    artifact_service = AsyncMock()

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    await orchestrator._run_job("job-3", "external-run-3")

    repository.update_job_status.assert_awaited_once_with("job-3", JobStatus.FAILED)
    notification_sink.notify_job_terminal.assert_called_once_with(failed_event)
    notification_sink.notify_user_left_and_complete.assert_called_once_with(failed_event)


@pytest.mark.asyncio
async def test_cancel_job_returns_false_when_external_id_is_missing() -> None:
    engine = AsyncMock()
    notification_sink = Mock()
    repository = AsyncMock()
    repository.get_job_external_id.return_value = None
    artifact_service = AsyncMock()

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    cancelled = await orchestrator.cancel_job("job-4")

    assert cancelled is False
    engine.cancel.assert_not_called()
    repository.update_job_status.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_job_updates_status_when_engine_accepts_cancellation() -> None:
    engine = AsyncMock()
    engine.cancel.return_value = True
    notification_sink = Mock()
    repository = AsyncMock()
    repository.get_job_external_id.return_value = "external-run-4"
    artifact_service = AsyncMock()

    orchestrator = TrainingOrchestrator(
        engine=engine,
        notification_sink=notification_sink,
        repository=repository,
        artifact_service=artifact_service,
    )

    cancelled = await orchestrator.cancel_job("job-4")

    assert cancelled is True
    engine.cancel.assert_awaited_once_with("external-run-4")
    repository.update_job_status.assert_awaited_once_with("job-4", JobStatus.CANCELLED)
