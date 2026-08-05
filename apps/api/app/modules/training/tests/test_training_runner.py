from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.modules.runtime.domain.context import TrainingRuntimeContext
from app.modules.runtime.domain.executables import RuntimeOperation
from app.modules.training.flows.train_job import execute_training_runtime


@pytest.mark.asyncio
async def test_training_runtime_host_only_builds_context_and_invokes_registration() -> None:
    app_context = object()
    with patch(
        "app.modules.training.flows.train_job.runtime_catalog.invoke",
        new_callable=AsyncMock,
        return_value={"status": "completed"},
    ) as invoke:
        result = await execute_training_runtime(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            created_by="user-1",
            missing_image_policy="fail",
            app_context=app_context,  # type: ignore[arg-type]
        )

    assert result == {"status": "completed"}
    assert invoke.await_args is not None
    operation, trainer_id, context = invoke.await_args.args
    assert operation is RuntimeOperation.TRAIN
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
            "app.modules.training.flows.train_job.runtime_catalog.invoke",
            new_callable=AsyncMock,
        ),
    ):
        await execute_training_runtime(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            created_by="user-1",
            missing_image_policy="fail",
        )

    close.assert_awaited_once_with(context)
