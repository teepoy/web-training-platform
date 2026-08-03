from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import JobStatus, PredictionJob
from app.workflows.train_predict import predict_stage


class _Injector:
    def __init__(
        self,
        prediction_repository: PredictionRepository,
        training_repository: TrainingRepository,
    ) -> None:
        self._prediction_repository = prediction_repository
        self._training_repository = training_repository

    def get(self, interface: object) -> object:
        if interface is PredictionRepository:
            return self._prediction_repository
        if interface is TrainingRepository:
            return self._training_repository
        raise LookupError(interface)


@pytest.mark.asyncio
async def test_predict_failure_preserves_model_and_marks_prediction_failed() -> None:
    prediction_repository = Mock(spec=PredictionRepository)
    prediction_repository.create_prediction_job = AsyncMock()
    prediction_repository.add_prediction_event = AsyncMock()
    prediction_repository.update_prediction_job_status = AsyncMock()
    training_repository = Mock(spec=TrainingRepository)
    training_repository.add_event = AsyncMock()

    prediction_job = PredictionJob(
        id="prediction-job-1",
        dataset_id="dataset-1",
        model_id="model-1",
        created_by="user-1",
        org_id="org-1",
        summary={"source_training_job_id": "training-job-1"},
    )
    prediction_repository.create_prediction_job.return_value = prediction_job

    context = Mock()
    context.injector = _Injector(
        prediction_repository,
        training_repository,
    )

    with (
        patch(
            "app.workflows.train_predict.build_flow_app_context",
            return_value=context,
        ),
        patch(
            "app.workflows.train_predict.close_flow_app_context",
            new_callable=AsyncMock,
        ),
        patch(
            "app.workflows.train_predict._run_prediction_job_with_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("prediction runtime failed"),
        ),
        patch(
            "app.workflows.train_predict.get_run_logger",
            return_value=Mock(),
        ),
    ):
        with pytest.raises(RuntimeError, match="prediction runtime failed"):
            await predict_stage.fn(
                source_training_job_id="training-job-1",
                dataset_id="dataset-1",
                model_id="model-1",
                org_id="org-1",
                created_by="user-1",
                target="image_classification",
                model_version=None,
                sample_ids=None,
                sample_filter=None,
                prompt=None,
                predictor_id="resnet50-sc-v1",
            )

    prediction_repository.update_prediction_job_status.assert_awaited_once()
    submitted_prediction_job = (
        prediction_repository.create_prediction_job.await_args.args[0]
    )
    assert submitted_prediction_job.summary["result_pool"] == "validation"
    status_call = prediction_repository.update_prediction_job_status.await_args
    assert status_call.args[:2] == ("prediction-job-1", JobStatus.FAILED)
    assert status_call.kwargs["summary"]["model_id"] == "model-1"
    assert status_call.kwargs["summary"]["retryable"] is True

    training_events = [
        call.args[0] for call in training_repository.add_event.await_args_list
    ]
    failure_event = training_events[-1]
    assert failure_event.payload["status"] == JobStatus.COMPLETED.value
    assert failure_event.payload["model_id"] == "model-1"
    assert failure_event.payload["prediction_status"] == JobStatus.FAILED.value
