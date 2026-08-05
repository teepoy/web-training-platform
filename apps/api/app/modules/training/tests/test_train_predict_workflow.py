from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.runtime.domain.context import TrainAndPredictRuntimeContext
from app.modules.runtime.domain.executables import RuntimeOperation
from app.workflows.train_predict import train_and_predict_flow


@pytest.mark.asyncio
async def test_train_and_predict_flow_invokes_registered_workflow() -> None:
    app_context = object()
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
            "app.workflows.train_predict.runtime_catalog.invoke",
            new_callable=AsyncMock,
            return_value={"model_id": "model-1"},
        ) as invoke,
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
            catalog_id="resnet50-sc-v1",
            input_contract="sc.patch_image.v1",
            owner="local_compat",
            missing_image_policy="skip",
        )

    assert result == {"model_id": "model-1"}
    assert invoke.await_args is not None
    operation, trainer_id, context = invoke.await_args.args
    assert operation is RuntimeOperation.TRAIN_AND_PREDICT
    assert trainer_id == "resnet50-sc-v1"
    assert isinstance(context, TrainAndPredictRuntimeContext)
