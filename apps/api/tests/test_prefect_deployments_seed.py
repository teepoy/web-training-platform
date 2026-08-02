from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.core.config import load_config
from app.core.platform_setup import prepare_prefect
from app.modules.runtime.app.services.deployment_seed import (
    platform_prefect_deployment_specs,
)
from app.shared.context import SharedInfra


def test_platform_prefect_deployment_specs_cover_runtime_and_cpu() -> None:
    config = load_config(skip_runtime_validation=True)
    specs = {
        spec["deployment_name"]: spec
        for spec in platform_prefect_deployment_specs(config)
    }

    assert {
        "train-job-deployment",
        "train-and-predict-deployment",
        "predict-job-batch-deployment",
        "timer-sensor",
        "dataset-size-sensor",
        "drain-dataset",
    } <= set(specs)
    assert specs["train-job-deployment"]["work_pool_name"] == "default-gpu"
    assert specs["timer-sensor"]["work_pool_name"] == "default-cpu"


@pytest.mark.anyio
async def test_prepare_prefect_ensures_pools_and_deployments(monkeypatch) -> None:
    config = load_config(skip_runtime_validation=True)
    prefect = AsyncMock()
    shared = MagicMock(spec=SharedInfra)
    shared.prefect_client = prefect
    validate = AsyncMock()
    monkeypatch.setattr("app.core.platform_setup.validate_prefect", validate)

    await prepare_prefect(config, shared)

    assert prefect.ensure_work_pool.await_args_list == [
        call("default-cpu", "process"),
        call("default-gpu", "process"),
    ]
    assert prefect.ensure_deployment.await_count == len(
        platform_prefect_deployment_specs(config)
    )
    validate.assert_awaited_once_with(config, shared)
