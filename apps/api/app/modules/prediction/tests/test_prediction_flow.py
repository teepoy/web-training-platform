from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.modules.prediction.flows.predict_job import (
    execute_prediction_runtime,
    predict_job_flow,
)
from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.runtime.domain.events import OperationCompleted


@pytest.mark.asyncio
async def test_prediction_runtime_host_only_invokes_registered_predictor() -> None:
    context = object()

    async def events():
        yield OperationCompleted({"processed": 2})

    with patch(
        "app.modules.prediction.flows.predict_job.runtime_catalog.stream_predict",
        new=Mock(return_value=events()),
    ) as stream:
        result = await execute_prediction_runtime(
            job_id="job-1",
            dataset_id="dataset-1",
            model_id="model-1",
            org_id="org-1",
            predictor_id="yolo-sc-v1",
            created_by="user-1",
            target="image_classification",
            app_context=context,  # type: ignore[arg-type]
        )

    assert result == {"processed": 2}
    assert stream.call_args is not None
    predictor_id, runtime_context = stream.call_args.args
    assert predictor_id == "yolo-sc-v1"
    assert isinstance(runtime_context, PredictionRuntimeContext)


@pytest.mark.asyncio
async def test_prediction_flow_invokes_runtime_host() -> None:
    with (
        patch(
            "app.modules.prediction.flows.predict_job.execute_prediction_runtime",
            new_callable=AsyncMock,
            return_value={"processed": 1},
        ) as execute,
        patch(
            "app.modules.prediction.flows.predict_job.get_run_logger",
            return_value=Mock(),
        ),
    ):
        result = await predict_job_flow.fn(
            job_id="job-1",
            dataset_id="dataset-1",
            model_id="model-1",
            org_id="org-1",
            predictor_id="yolo-sc-v1",
        )

    assert result == {"processed": 1}
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_prediction_flow_passes_collection_revision_source_to_runtime() -> None:
    with (
        patch(
            "app.modules.prediction.flows.predict_job.execute_prediction_runtime",
            new_callable=AsyncMock,
            return_value={"processed": 2},
        ) as execute,
        patch(
            "app.modules.prediction.flows.predict_job.get_run_logger",
            return_value=Mock(),
        ),
    ):
        await predict_job_flow.fn(
            job_id="job-collection",
            dataset_id=None,
            collection_id="collection-1",
            collection_revision_id="revision-1",
            model_id="model-1",
            org_id="org-1",
            predictor_id="yolo-sc-v1",
        )

    assert execute.await_args is not None
    assert execute.await_args.kwargs["dataset_id"] is None
    assert execute.await_args.kwargs["collection_id"] == "collection-1"
    assert execute.await_args.kwargs["collection_revision_id"] == "revision-1"
