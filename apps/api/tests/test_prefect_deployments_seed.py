from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from omegaconf import OmegaConf

from app.main import _ensure_prefect_deployments


@pytest.mark.anyio
async def test_ensure_prefect_deployments_all_entries() -> None:
    cfg = OmegaConf.create({
        "execution": {"engine": "prefect"},
    })
    mock_client = AsyncMock()

    await _ensure_prefect_deployments(cfg, mock_client)

    assert mock_client.ensure_deployment.call_count == 7

    calls = mock_client.ensure_deployment.call_args_list
    called: list[dict] = []
    for call in calls:
        called.append(call.kwargs)

    # ── GPU pool ──
    assert {
        "deployment_name": "train-job-deployment",
        "flow_name": "training-train-job",
        "work_pool_name": "default-gpu",
        "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
        "path": "",
    } in called

    assert {
        "deployment_name": "train-and-predict-deployment",
        "flow_name": "training-train-and-predict",
        "work_pool_name": "default-gpu",
        "entrypoint": "app.modules.training.flows.train_predict:train_and_predict_flow",
        "path": "",
    } in called

    assert {
        "deployment_name": "predict-job-batch-deployment",
        "flow_name": "prediction-predict-job",
        "work_pool_name": "default-gpu",
        "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
        "path": "",
    } in called

    assert {
        "deployment_name": "embed-job-batch-deployment",
        "flow_name": "embedding-embed",
        "work_pool_name": "default-gpu",
        "entrypoint": "app.modules.embedding.flows.embed:embed_flow",
        "path": "",
    } in called

    assert {
        "deployment_name": "timer-sensor",
        "flow_name": "timer-sensor",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.sensors.adapter.flows.timer_sensor:timer_sensor",
        "path": "",
    } in called

    assert {
        "deployment_name": "dataset-size-sensor",
        "flow_name": "dataset-size-sensor",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.sensors.adapter.flows.dataset_size_sensor:dataset_size_sensor",
        "path": "",
    } in called

    assert {
        "deployment_name": "drain-dataset",
        "flow_name": "drain-dataset",
        "work_pool_name": "default-cpu",
        "entrypoint": "app.modules.datasets.adapter.flows.drain_dataset:drain_dataset",
        "path": "",
    } in called


@pytest.mark.anyio
async def test_ensure_prefect_deployments_skips_when_engine_not_prefect() -> None:
    cfg = OmegaConf.create({
        "execution": {"engine": "local"},
    })
    mock_client = AsyncMock()

    await _ensure_prefect_deployments(cfg, mock_client)

    mock_client.ensure_deployment.assert_not_called()


@pytest.mark.anyio
async def test_ensure_prefect_deployments_swallows_errors_per_entry() -> None:
    cfg = OmegaConf.create({
        "execution": {"engine": "prefect"},
    })
    mock_client = AsyncMock()
    mock_client.ensure_deployment.side_effect = [
        Exception("first fails"),
        None,
        None,
        None,
        None,
        None,
        None,
    ]

    await _ensure_prefect_deployments(cfg, mock_client)

    assert mock_client.ensure_deployment.call_count == 7
