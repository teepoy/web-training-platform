from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.core.platform_setup import prepare_prefect
from app.modules.runtime.app.services.deployment_catalog import (
    platform_prefect_deployment_specs,
)
from app.shared.context import SharedInfra


def test_platform_prefect_deployment_specs_cover_runtime_and_cpu() -> None:
    specs = {
        spec["deployment_name"]: spec
        for spec in platform_prefect_deployment_specs()
    }

    assert {
        "train-job-deployment",
        "train-and-predict-deployment",
        "predict-job-batch-deployment",
        "predict-job-batch-automation-deployment",
        "collection-discovery-poll",
        "drain-dataset",
    } <= set(specs)
    assert specs["train-job-deployment"]["work_pool_name"] == "default-gpu"
    assert specs["collection-discovery-poll"]["work_pool_name"] == "default-cpu"
    assert specs["collection-discovery-poll"]["schedules"] == [
        {
            "schedule": {"cron": "*/5 * * * *", "timezone": "UTC"},
            "active": True,
        }
    ]


@pytest.mark.anyio
async def test_prepare_prefect_ensures_pools_and_deployments(monkeypatch) -> None:
    prefect = AsyncMock()
    shared = MagicMock(spec=SharedInfra)
    shared.prefect_client = prefect
    validate = AsyncMock()
    monkeypatch.setattr("app.core.platform_setup.validate_prefect", validate)

    await prepare_prefect(shared)

    assert prefect.ensure_work_pool.await_args_list == [
        call("default-cpu", "process"),
        call("default-gpu", "process"),
    ]
    assert prefect.ensure_work_queue.await_args_list == [
        call("default-gpu", "prediction-manual", priority=1),
        call("default-gpu", "prediction-automation", priority=10),
    ]
    assert prefect.ensure_deployment.await_count == len(
        platform_prefect_deployment_specs()
    )
    validate.assert_awaited_once_with(shared)
