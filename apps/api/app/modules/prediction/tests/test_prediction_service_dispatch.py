from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.prediction.app.services.prediction_runtime import (
    PredictionRuntimeService,
)
from app.shared.api.schemas import Dataset, Model, TaskSpec


@pytest.mark.asyncio
async def test_single_prediction_uses_direct_deployment_and_command_parameters() -> None:
    dataset_reader = Mock()
    dataset_reader.get_dataset = AsyncMock(
        return_value=Dataset(
            id="dataset-1",
            name="dataset",
            dataset_type="image_sc",
            task_spec=TaskSpec(
                task_type="sc",
                label_space=["cat", "dog"],
            ),
            view_types=["patch_image_v1"],
        )
    )
    model_catalog = Mock()
    model_catalog.get_model = AsyncMock(
        return_value=Model(
            id="model-1",
            uri="memory://model",
            kind="model",
            job_id="training-1",
            trainer_id="yolo-sc-v1",
            metadata={
                "dataset_types": ["image_sc"],
                "task_types": ["sc"],
                "prediction_targets": ["image_classification"],
                "label_space": ["cat", "dog"],
                "model_contract": "sc.yolo.model.v1",
                "model_schema_version": "1",
            },
        )
    )
    service = PredictionRuntimeService(
        dataset_reader=dataset_reader,
        model_catalog=model_catalog,
    )

    with patch(
        "app.modules.prediction.app.services.prediction_runtime."
        "submit_flow_run_and_wait",
        new=AsyncMock(
            return_value={
                "predictions": [
                    {
                        "sample_id": "sample-1",
                        "predicted_label": "cat",
                        "confidence": 0.9,
                    }
                ]
            }
        ),
    ) as submit:
        result = await service.predict_single(
            model_id="model-1",
            dataset_id="dataset-1",
            sample_id="sample-1",
            org_id="org-1",
        )

    assert result.predicted_label == "cat"
    submit.assert_awaited_once()
    await_args = submit.await_args
    assert await_args is not None
    assert await_args.kwargs["deployment_name"] == "predict-job-batch-deployment"
    parameters = await_args.kwargs["parameters"]
    assert parameters["sample_ids"] == ["sample-1"]
    assert parameters["predictor_id"] == "yolo-sc-v1"
    assert "catalog_id" not in parameters
