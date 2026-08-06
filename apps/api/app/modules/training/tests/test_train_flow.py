from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.training.flows.train_job import train_job_flow


@pytest.mark.asyncio
async def test_train_flow_invokes_registered_runtime_host() -> None:
    with (
        patch(
            "app.modules.training.flows.train_job.execute_training_runtime",
            new_callable=AsyncMock,
            return_value={"status": "completed"},
        ) as execute,
        patch(
            "app.modules.training.flows.train_job.get_run_logger",
            return_value=Mock(),
        ),
    ):
        result = await train_job_flow.fn(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            created_by="user-1",
        )

    assert result == {"status": "completed"}
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_train_flow_passes_collection_revision_source_to_runtime() -> None:
    with (
        patch(
            "app.modules.training.flows.train_job.execute_training_runtime",
            new_callable=AsyncMock,
            return_value={"status": "completed"},
        ) as execute,
        patch(
            "app.modules.training.flows.train_job.get_run_logger",
            return_value=Mock(),
        ),
    ):
        await train_job_flow.fn(
            job_id="job-collection",
            dataset_id=None,
            collection_id="collection-1",
            collection_revision_id="revision-1",
            org_id="org-1",
            trainer_id="resnet50-sc-v1",
        )

    assert execute.await_args is not None
    assert execute.await_args.kwargs["dataset_id"] is None
    assert execute.await_args.kwargs["collection_id"] == "collection-1"
    assert execute.await_args.kwargs["collection_revision_id"] == "revision-1"
