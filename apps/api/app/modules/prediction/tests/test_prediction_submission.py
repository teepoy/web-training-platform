from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.prediction.app.services.submission_service import (
    PredictionSubmissionService,
)
from app.modules.prediction.domain.submission import (
    PredictionJobCommand,
    PredictionRuntimeUnavailableError,
)
from app.modules.runtime.domain.routing import RuntimeDeploymentRoute


def _command() -> PredictionJobCommand:
    return PredictionJobCommand(
        dataset_id="dataset-1",
        model_id="model-1",
        org_id="org-1",
        created_by="user-1",
        sample_ids=("sample-1",),
        prompt="classify",
    )


def _submission(*, deployment_id: str | None = "deployment-1"):
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(
        return_value=SimpleNamespace(view_types=["patch_image_v1"])
    )
    model_catalog = Mock()
    model_catalog.get_model = AsyncMock(
        return_value=SimpleNamespace(
            trainer_id="resnet50-sc-v1",
            trainer_name=None,
            metadata={
                "model_contract": "sc.resnet50.model.v1",
                "model_schema_version": "1",
            },
        )
    )
    repository = Mock()
    repository.create_prediction_job = AsyncMock(side_effect=lambda job, **_: job)
    repository.set_prediction_job_external_id = AsyncMock()
    repository.add_prediction_event = AsyncMock()
    repository.update_prediction_job_status = AsyncMock()
    repository.get_prediction_job = AsyncMock(return_value=None)
    prefect_client = Mock()
    prefect_client.resolve_deployment_id = AsyncMock(return_value=deployment_id)
    prefect_client.create_flow_run_from_deployment = AsyncMock(
        return_value={"id": "flow-run-1"}
    )
    runtime_router = Mock()
    runtime_router.prediction_route.return_value = RuntimeDeploymentRoute(
        catalog_id="resnet50-sc-v1",
        deployment="prediction-predict-job",
        input_contract="sc.patch_image.v1",
        output_contract="prediction.table.v1",
        resource_profile="gpu",
        owner="local_compat",
    )
    submission = PredictionSubmissionService(
        prefect_client=prefect_client,
        repository=repository,
        runtime_router=runtime_router,
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
    )
    return submission, repository, prefect_client


@pytest.mark.asyncio
async def test_submission_validates_runtime_before_persisting_job() -> None:
    submission, repository, _prefect_client = _submission(deployment_id=None)

    with pytest.raises(PredictionRuntimeUnavailableError, match="not registered"):
        await submission.submit_job(_command())

    repository.create_prediction_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_submission_builds_runtime_parameters_from_command_and_route() -> None:
    submission, repository, prefect_client = _submission()
    submission._poll_run = AsyncMock()

    job = await submission.submit_job(_command())

    repository.create_prediction_job.assert_awaited_once()
    prefect_client.create_flow_run_from_deployment.assert_awaited_once()
    parameters = (
        prefect_client.create_flow_run_from_deployment.await_args.kwargs["parameters"]
    )
    assert parameters["job_id"] == job.id
    assert parameters["sample_ids"] == ["sample-1"]
    assert parameters["prompt"] == "classify"
    assert parameters["catalog_id"] == "resnet50-sc-v1"
