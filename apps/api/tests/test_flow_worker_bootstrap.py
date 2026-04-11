from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from app.flows import serve


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

    with patch("app.flows.serve.load_config", return_value=cfg), patch(
        "app.flows.serve.PrefectClient", return_value=client
    ):
        await serve._ensure_work_pool("training-pool")

    client.ensure_work_pool.assert_awaited_once_with(
        name="training-pool",
        type="process",
        concurrency_limit=3,
    )


@pytest.mark.asyncio
async def test_bootstrap_gpu_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.train_job.ato_deployment",
        new=AsyncMock(return_value=deployment),
    ) as ato_deployment:
        await serve._bootstrap_worker_deployment("training-pool", "train-gpu")

    ensure_pool.assert_awaited_once_with("training-pool")
    ato_deployment.assert_awaited_once_with(
        name="train-job-torch-deployment",
        description="Torch runtime deployment for train-job flow (managed by delegated worker)",
        work_pool_name="training-pool",
        work_queue_name="train-gpu",
    )
    deployment.aapply.assert_awaited_once_with(work_pool_name="training-pool")


@pytest.mark.asyncio
async def test_bootstrap_dspy_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.train_job.ato_deployment",
        new=AsyncMock(return_value=deployment),
    ) as ato_deployment:
        await serve._bootstrap_worker_deployment("training-pool", "optimize-llm-cpu")

    ensure_pool.assert_awaited_once_with("training-pool")
    ato_deployment.assert_awaited_once_with(
        name="train-job-dspy-deployment",
        description="DSPy runtime deployment for train-job flow (managed by delegated worker)",
        work_pool_name="training-pool",
        work_queue_name="optimize-llm-cpu",
    )
    deployment.aapply.assert_awaited_once_with(work_pool_name="training-pool")


@pytest.mark.asyncio
async def test_bootstrap_rejects_unknown_queue() -> None:
    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("training-pool", "unknown")

    assert "Unsupported WORK_QUEUE_NAME 'unknown'" in str(exc_info.value)
