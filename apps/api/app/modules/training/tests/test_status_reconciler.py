from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.training.app.services.status_reconciler import (
    TrainingStatusReconciler,
)
from app.modules.training.domain.repository import ActiveTrainingExecution
from app.shared.api.schemas import JobStatus


def _reconciler(
    *,
    current: JobStatus,
    backend: JobStatus,
) -> tuple[TrainingStatusReconciler, Mock, Mock]:
    repository = Mock()
    repository.list_active_executions = AsyncMock(
        return_value=[
            ActiveTrainingExecution(
                job_id="job-1",
                external_job_id="run-1",
                status=current,
            )
        ]
    )
    repository.update_job_status = AsyncMock(return_value=True)
    repository.add_event = AsyncMock()
    engine = Mock()
    engine.status = AsyncMock(return_value=backend)
    notifications = Mock()
    return (
        TrainingStatusReconciler(
            engine=engine,
            repository=repository,
            notification_sink=notifications,
            interval_seconds=1,
        ),
        repository,
        notifications,
    )


@pytest.mark.asyncio
async def test_reconciler_restores_terminal_status_after_api_restart() -> None:
    reconciler, repository, notifications = _reconciler(
        current=JobStatus.RUNNING,
        backend=JobStatus.COMPLETED,
    )

    await reconciler.reconcile_once()

    repository.update_job_status.assert_awaited_once_with(
        "job-1",
        JobStatus.COMPLETED,
    )
    event = repository.add_event.await_args.args[0]
    assert event.payload == {
        "status": "completed",
        "source": "execution_reconciler",
    }
    notifications.notify_job_terminal.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_reconciler_does_not_rewrite_unchanged_status() -> None:
    reconciler, repository, notifications = _reconciler(
        current=JobStatus.RUNNING,
        backend=JobStatus.RUNNING,
    )

    await reconciler.reconcile_once()

    repository.update_job_status.assert_not_awaited()
    repository.add_event.assert_not_awaited()
    notifications.notify_job_update.assert_not_called()
    notifications.notify_job_terminal.assert_not_called()
