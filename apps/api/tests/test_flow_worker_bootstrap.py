from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from app.shared.infrastructure.prefect import flow_serve as serve


def test_deployment_root_uses_container_stable_api_workspace() -> None:
    assert serve._DEPLOYMENT_ROOT == "/app/apps/api"


@pytest.mark.asyncio
async def test_ensure_work_pool_uses_config() -> None:
    cfg = SimpleNamespace(
        prefect=SimpleNamespace(
            api_url="http://prefect.example/api",
            work_pool_type="process",
            concurrency_limit=3,
        )
    )
    client = AsyncMock()

    with patch("app.shared.infrastructure.prefect.flow_serve.load_config", return_value=cfg), patch(
        "app.shared.infrastructure.prefect.flow_serve.PrefectClient", return_value=client
    ):
        await serve._ensure_work_pool("training-pool")

    client.ensure_work_pool.assert_awaited_once_with(
        name="training-pool",
        type="process",
        concurrency_limit=3,
    )


@pytest.mark.asyncio
async def test_bootstrap_rejects_retired_gpu_queue() -> None:
    """V2 is CPU-only. Retired GPU queues (train-gpu) must raise RuntimeError."""
    with patch("app.shared.infrastructure.prefect.flow_serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("training-pool", "train-gpu")

    assert "Unsupported WORK_QUEUE_NAME 'train-gpu'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bootstrap_dspy_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "train-dspy-deployment-id"

    with patch(
        "app.shared.infrastructure.prefect.flow_serve._ensure_work_pool",
        new=AsyncMock(),
    ) as ensure_pool, patch(
        "app.shared.infrastructure.prefect.flow_serve.load_config",
        return_value=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api")),
    ), patch(
        "app.shared.infrastructure.prefect.flow_serve.PrefectClient",
        return_value=client,
    ), patch(
        "app.shared.infrastructure.prefect.flow_serve.train_job.ato_deployment",
        new=AsyncMock(return_value=deployment),
    ) as ato_deployment:
        await serve._bootstrap_worker_deployment("training-pool", "optimize-llm-cpu")

    ensure_pool.assert_awaited_once_with("default-pool")
    ato_deployment.assert_awaited_once_with(
        name="train-job-dspy-deployment",
        description="DSPy runtime deployment for train-job flow (managed by delegated worker)",
        work_pool_name="default-pool",
        work_queue_name="optimize-llm-cpu",
    )
    deployment.aapply.assert_awaited_once_with(work_pool_name="default-pool")
    client.resolve_deployment_id.assert_awaited_once_with("train-job-dspy-deployment")
    client._request.assert_awaited_once_with(
        "PATCH",
        "/deployments/train-dspy-deployment-id",
        json={
            "entrypoint": "app/modules/training/infrastructure/flows/train_job.py:train_job",
            "path": serve._DEPLOYMENT_ROOT,
        },
        expect_json=False,
        resource_label="deployment",
    )
    assert client._request.await_args.kwargs["json"]["path"] == "/app/apps/api"


@pytest.mark.asyncio
async def test_bootstrap_rejects_retired_predict_queue() -> None:
    """V2 is CPU-only. Retired predict-batch queue must raise RuntimeError."""
    with patch("app.shared.infrastructure.prefect.flow_serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("predict-pool", "predict-batch")

    assert "Unsupported WORK_QUEUE_NAME 'predict-batch'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bootstrap_rejects_retired_embed_queue() -> None:
    """V2 is CPU-only. Retired embed-batch queue must raise RuntimeError."""
    with patch("app.shared.infrastructure.prefect.flow_serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("embed-pool", "embed-batch")

    assert "Unsupported WORK_QUEUE_NAME 'embed-batch'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bootstrap_rejects_unknown_queue() -> None:
    with patch("app.shared.infrastructure.prefect.flow_serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("training-pool", "unknown")

    assert "Unsupported WORK_QUEUE_NAME 'unknown'" in str(exc_info.value)
