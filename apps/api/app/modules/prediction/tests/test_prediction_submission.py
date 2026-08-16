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
    PredictionSubmissionOrigin,
)


def _command(
    *,
    submission_origin: PredictionSubmissionOrigin = PredictionSubmissionOrigin.MANUAL,
) -> PredictionJobCommand:
    return PredictionJobCommand(
        dataset_id="dataset-1",
        model_id="model-1",
        org_id="org-1",
        created_by="user-1",
        sample_ids=("sample-1",),
        prompt="classify",
        submission_origin=submission_origin,
    )


def _submission(*, deployment_id: str | None = "deployment-1"):
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(
        return_value=SimpleNamespace(view_types=["patch_image_v1"])
    )
    model_catalog = Mock()
    model_catalog.get_model = AsyncMock(
        return_value=SimpleNamespace(
            trainer_id="yolo-sc-v1",
            trainer_name=None,
            metadata={
                "model_contract": "sc.yolo.model.v1",
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
    dataset_revisions = Mock()
    dataset_revisions.resolve_or_create_baseline = AsyncMock(
        return_value=SimpleNamespace(id="revision-1")
    )
    prefect_client = Mock()
    prefect_client.resolve_deployment_id = AsyncMock(return_value=deployment_id)
    prefect_client.create_flow_run_from_deployment = AsyncMock(
        return_value={"id": "flow-run-1"}
    )
    submission = PredictionSubmissionService(
        prefect_client=prefect_client,
        repository=repository,
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
        dataset_revisions=dataset_revisions,
    )
    return submission, repository, prefect_client, dataset_revisions


@pytest.mark.asyncio
async def test_submission_validates_runtime_before_persisting_job() -> None:
    submission, repository, _prefect_client, _dataset_revisions = _submission(
        deployment_id=None
    )

    with pytest.raises(PredictionRuntimeUnavailableError, match="not registered"):
        await submission.submit_job(_command())

    repository.create_prediction_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_submission_builds_minimal_runtime_parameters() -> None:
    submission, repository, prefect_client, dataset_revisions = _submission()
    submission._poll_run = AsyncMock()

    job = await submission.submit_job(_command())

    repository.create_prediction_job.assert_awaited_once()
    persisted_job = repository.create_prediction_job.await_args.args[0]
    assert persisted_job.dataset_revision_id == "revision-1"
    assert persisted_job.summary["submission_origin"] == "manual"
    dataset_revisions.resolve_or_create_baseline.assert_awaited_once_with(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
    )
    prefect_client.create_flow_run_from_deployment.assert_awaited_once()
    parameters = prefect_client.create_flow_run_from_deployment.await_args.kwargs[
        "parameters"
    ]
    assert parameters["job_id"] == job.id
    assert parameters["sample_ids"] == ["sample-1"]
    assert parameters["prompt"] == "classify"
    assert parameters["predictor_id"] == "yolo-sc-v1"
    assert "output_contract" not in parameters
    assert "resource_profile" not in parameters
    prefect_client.resolve_deployment_id.assert_awaited_once_with(
        "predict-job-batch-deployment"
    )


@pytest.mark.asyncio
async def test_automation_submission_uses_lower_priority_deployment() -> None:
    submission, _repository, prefect_client, _dataset_revisions = _submission()
    submission._poll_run = AsyncMock()

    await submission.submit_job(
        _command(submission_origin=PredictionSubmissionOrigin.AUTOMATION)
    )

    prefect_client.resolve_deployment_id.assert_awaited_once_with(
        "predict-job-batch-automation-deployment"
    )


@pytest.mark.asyncio
async def test_dataset_prediction_can_record_collection_provenance() -> None:
    submission, repository, prefect_client, _dataset_revisions = _submission()
    submission._poll_run = AsyncMock()
    command = PredictionJobCommand(
        dataset_id="dataset-1",
        collection_id="collection-1",
        collection_revision_id="snapshot-1",
        model_id="model-1",
        org_id="org-1",
        created_by="user-1",
        collection_prediction_batch_id="batch-1",
        collection_member_id="member-1",
    )

    await submission.submit_job(command)

    persisted_job = repository.create_prediction_job.await_args.args[0]
    assert persisted_job.dataset_id == "dataset-1"
    assert persisted_job.collection_id == "collection-1"
    assert persisted_job.collection_revision_id == "snapshot-1"
    assert persisted_job.summary["collection_prediction_batch_id"] == "batch-1"
    assert persisted_job.summary["collection_member_id"] == "member-1"
    parameters = prefect_client.create_flow_run_from_deployment.await_args.kwargs[
        "parameters"
    ]
    assert parameters["dataset_id"] == "dataset-1"
    assert parameters["collection_id"] == "collection-1"
    assert parameters["collection_revision_id"] == "snapshot-1"
