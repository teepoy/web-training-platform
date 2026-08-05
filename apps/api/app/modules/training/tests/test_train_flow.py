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
            catalog_id="resnet50-sc-v1",
            input_contract="sc.patch_image.v1",
            output_contract="sc.resnet50.model.v1",
            resource_profile="gpu",
            owner="local_compat",
            algo_id="resnet50-sc",
            algo_version="1",
            missing_image_policy="fail",
        )

    assert result == {"status": "completed"}
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_train_flow_rejects_mismatched_catalog_id() -> None:
    with pytest.raises(ValueError, match="catalog_id matching trainer_id"):
        await train_job_flow.fn(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            catalog_id="yolo-sc-v1",
        )
