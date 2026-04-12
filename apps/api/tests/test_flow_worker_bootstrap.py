from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from app.flows import serve


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
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "train-gpu-deployment-id"

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.load_config",
        return_value=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api")),
    ), patch(
        "app.flows.serve.PrefectClient",
        return_value=client,
    ), patch(
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
    client.resolve_deployment_id.assert_awaited_once_with("train-job-torch-deployment")
    client._request.assert_awaited_once_with(
        "PATCH",
        "/deployments/train-gpu-deployment-id",
        json={"entrypoint": "app/flows/train_job.py:train_job", "path": serve._DEPLOYMENT_ROOT},
        expect_json=False,
        resource_label="deployment",
    )
    assert client._request.await_args.kwargs["json"]["path"] == "/app/apps/api"


@pytest.mark.asyncio
async def test_bootstrap_dspy_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "train-dspy-deployment-id"

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.load_config",
        return_value=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api")),
    ), patch(
        "app.flows.serve.PrefectClient",
        return_value=client,
    ), patch(
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
    client.resolve_deployment_id.assert_awaited_once_with("train-job-dspy-deployment")
    client._request.assert_awaited_once_with(
        "PATCH",
        "/deployments/train-dspy-deployment-id",
        json={"entrypoint": "app/flows/train_job.py:train_job", "path": serve._DEPLOYMENT_ROOT},
        expect_json=False,
        resource_label="deployment",
    )
    assert client._request.await_args.kwargs["json"]["path"] == "/app/apps/api"


@pytest.mark.asyncio
async def test_bootstrap_prediction_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "predict-deployment-id"

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.load_config",
        return_value=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api")),
    ), patch(
        "app.flows.serve.PrefectClient",
        return_value=client,
    ), patch(
        "app.flows.serve.predict_job.ato_deployment",
        new=AsyncMock(return_value=deployment),
    ) as ato_deployment:
        await serve._bootstrap_worker_deployment("training-pool", "predict-batch")

    ensure_pool.assert_awaited_once_with("predict-pool")
    ato_deployment.assert_awaited_once_with(
        name="predict-job-batch-deployment",
        description="Prediction runtime deployment for predict-job flow (managed by delegated worker)",
        work_pool_name="predict-pool",
        work_queue_name="predict-batch",
    )
    deployment.aapply.assert_awaited_once_with(work_pool_name="predict-pool")
    client.resolve_deployment_id.assert_awaited_once_with("predict-job-batch-deployment")
    client._request.assert_awaited_once_with(
        "PATCH",
        "/deployments/predict-deployment-id",
        json={"entrypoint": "app/flows/predict_job.py:predict_job", "path": serve._DEPLOYMENT_ROOT},
        expect_json=False,
        resource_label="deployment",
    )
    assert client._request.await_args.kwargs["json"]["path"] == "/app/apps/api"


@pytest.mark.asyncio
async def test_bootstrap_embedding_worker_registers_owned_deployment() -> None:
    deployment = AsyncMock()
    deployment.aapply = AsyncMock()
    client = AsyncMock()
    client.resolve_deployment_id.return_value = "embed-deployment-id"

    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()) as ensure_pool, patch(
        "app.flows.serve.load_config",
        return_value=SimpleNamespace(prefect=SimpleNamespace(api_url="http://prefect.example/api")),
    ), patch(
        "app.flows.serve.PrefectClient",
        return_value=client,
    ), patch(
        "app.flows.serve.predict_job.ato_deployment",
        new=AsyncMock(return_value=deployment),
    ) as ato_deployment:
        await serve._bootstrap_worker_deployment("training-pool", "embed-batch")

    ensure_pool.assert_awaited_once_with("embed-pool")
    ato_deployment.assert_awaited_once_with(
        name="embed-job-batch-deployment",
        description="Embedding runtime deployment for predict-job flow (managed by delegated worker)",
        work_pool_name="embed-pool",
        work_queue_name="embed-batch",
    )
    deployment.aapply.assert_awaited_once_with(work_pool_name="embed-pool")
    client.resolve_deployment_id.assert_awaited_once_with("embed-job-batch-deployment")
    client._request.assert_awaited_once_with(
        "PATCH",
        "/deployments/embed-deployment-id",
        json={"entrypoint": "app/flows/predict_job.py:predict_job", "path": serve._DEPLOYMENT_ROOT},
        expect_json=False,
        resource_label="deployment",
    )
    assert client._request.await_args.kwargs["json"]["path"] == "/app/apps/api"


@pytest.mark.asyncio
async def test_bootstrap_rejects_unknown_queue() -> None:
    with patch("app.flows.serve._ensure_work_pool", new=AsyncMock()):
        with pytest.raises(RuntimeError) as exc_info:
            await serve._bootstrap_worker_deployment("training-pool", "unknown")

    assert "Unsupported WORK_QUEUE_NAME 'unknown'" in str(exc_info.value)
