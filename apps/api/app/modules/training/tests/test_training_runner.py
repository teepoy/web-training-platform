from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.events import OperationCompleted
from app.modules.training.flows.train_job import execute_training_runtime


@pytest.mark.asyncio
async def test_training_runtime_host_only_builds_context_and_invokes_registration() -> None:
    app_context = object()

    async def events():
        yield OperationCompleted({"status": "completed"})

    with patch(
        "app.modules.training.flows.train_job.runtime_catalog.stream_train",
        new=Mock(return_value=events()),
    ) as stream:
        result = await execute_training_runtime(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            created_by="user-1",
            app_context=app_context,  # type: ignore[arg-type]
        )

    assert result == {"status": "completed"}
    assert stream.call_args is not None
    trainer_id, context = stream.call_args.args
    assert trainer_id == "resnet50-sc-v1"
    assert isinstance(context, TrainingRuntimeContext)
    assert context.app_context is app_context


@pytest.mark.asyncio
async def test_training_runtime_host_closes_owned_context() -> None:
    context = object()
    with (
        patch(
            "app.modules.training.flows.train_job.build_flow_app_context",
            return_value=context,
        ),
        patch(
            "app.modules.training.flows.train_job.close_flow_app_context",
            new_callable=AsyncMock,
        ) as close,
        patch(
            "app.modules.training.flows.train_job.runtime_catalog.stream_train",
            new=Mock(return_value=_completed_events()),
        ),
    ):
        await execute_training_runtime(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            created_by="user-1",
        )

    close.assert_awaited_once_with(context)


async def _completed_events():
    yield OperationCompleted()
