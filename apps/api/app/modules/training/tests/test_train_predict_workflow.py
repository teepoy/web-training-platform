from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.runtime.domain.context import TrainAndPredictRuntimeContext
from app.modules.runtime.domain.events import OperationCompleted
from app.modules.training.app.services.preflight import TrainingPreflightService
from app.workflows.train_predict import train_and_predict_flow


@pytest.mark.asyncio
async def test_train_and_predict_flow_invokes_registered_workflow() -> None:
    preflight = Mock()
    preflight.ensure_ready = AsyncMock()
    injector = Mock()
    injector.get.side_effect = lambda dependency: (
        preflight if dependency is TrainingPreflightService else object()
    )
    app_context = SimpleNamespace(injector=injector)

    async def events():
        yield OperationCompleted({"model_id": "model-1"})

    with (
        patch(
            "app.workflows.train_predict.build_flow_app_context",
            return_value=app_context,
        ),
        patch(
            "app.workflows.train_predict.close_flow_app_context",
            new_callable=AsyncMock,
        ),
        patch(
            "app.workflows.train_predict.runtime_catalog.stream_train_and_predict",
            new=Mock(return_value=events()),
        ) as stream,
        patch(
            "app.workflows.train_predict.get_run_logger",
            return_value=Mock(),
        ),
    ):
        result = await train_and_predict_flow.fn(
            job_id="job-1",
            dataset_id="dataset-1",
            trainer_id="resnet50-sc-v1",
            org_id="org-1",
            predictor_id="resnet50-sc-v1",
        )

    assert result == {"model_id": "model-1"}
    assert stream.call_args is not None
    trainer_id, context = stream.call_args.args
    assert trainer_id == "resnet50-sc-v1"
    assert isinstance(context, TrainAndPredictRuntimeContext)
    preflight.ensure_ready.assert_awaited_once()
