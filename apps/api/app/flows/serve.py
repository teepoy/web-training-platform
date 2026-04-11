"""Flow worker entrypoint.

Run with:
    python -m app.flows.serve

This starts a long-lived process that polls Prefect server for scheduled runs.

Embedded runner (default path)
------------------------------
The API process starts the V1 runner automatically during its FastAPI lifespan
when ``execution.engine`` is set to ``prefect``.  See ``app.main._run_prefect_runner``.

This module can still be run standalone (``python -m app.flows.serve``) for the
delegated training workers, which use V2 work-pool mode.

V1 strategy
-----------
We use ``prefect.runner.Runner`` to register and serve deployments for every flow
defined in this package.  On startup the runner:

1. Registers a default deployment per flow (``{flow_name}-deployment``) so
   at least one always exists.
2. Picks up scheduled/triggered runs for those deployments.

Deployments created through the platform UI (which hit the Prefect REST API
directly) will also appear on the server.  The runner only executes runs for
its own served deployments — this is a known limitation.

V2 strategy
-----------
The worker first bootstraps the deployment it owns, then starts a Prefect
worker process for the matching work queue. This keeps deployment ownership
aligned with queue ownership.

Set ``WORKER_MODE=v2`` to activate this path.

Environment variables
---------------------
PREFECT_API_URL     — Prefect server URL (set by compose).
PLATFORM_API_URL    — Platform API URL for flow callbacks (e.g. ``http://api:8000``).
WORKER_MODE         — ``v1`` (default) or ``v2``.
WORK_POOL_NAME      — Work pool name for V2 mode (default ``training-pool``).
WORK_QUEUE_NAME     — Work queue name for V2 mode (required for specialized workers).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import os
import subprocess
import sys

from prefect.runner import Runner

from app.core.config import load_config
from app.flows.drain_dataset import drain_dataset
from app.flows.predict_job import predict_job  # noqa: F401 — register flow for V2 worker
from app.flows.train_job import train_job  # noqa: F401 — register flow for V2 worker
from app.services.prefect_client import PrefectClient


_GPU_QUEUE = "train-gpu"
_DSPY_QUEUE = "optimize-llm-cpu"
_PREDICT_QUEUE = "predict-batch"
_DEPLOYMENT_ROOT = str(Path(__file__).resolve().parents[2])
_FLOW_ENTRYPOINT = "app/flows/train_job.py:train_job"
_DRAIN_ENTRYPOINT = "app/flows/drain_dataset.py:drain_dataset"
_PREDICT_ENTRYPOINT = "app/flows/predict_job.py:predict_job"


async def _ensure_work_pool(pool_name: str) -> None:
    cfg = load_config()
    client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))
    await client.ensure_work_pool(
        name=pool_name,
        type=str(cfg.prefect.work_pool_type),
        concurrency_limit=int(cfg.prefect.concurrency_limit),
    )


async def _bootstrap_worker_deployment(pool_name: str, queue_name: str) -> None:
    deployment: Any | None = None
    deployment_name = ""

    await _ensure_work_pool(pool_name)
    cfg = load_config()
    client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))

    if queue_name == _GPU_QUEUE:
        deployment_name = "train-job-torch-deployment"
        deployment = await train_job.ato_deployment(
            name=deployment_name,
            description="Torch runtime deployment for train-job flow (managed by delegated worker)",
            work_pool_name=pool_name,
            work_queue_name=queue_name,
        )
    elif queue_name == _DSPY_QUEUE:
        deployment_name = "train-job-dspy-deployment"
        deployment = await train_job.ato_deployment(
            name=deployment_name,
            description="DSPy runtime deployment for train-job flow (managed by delegated worker)",
            work_pool_name=pool_name,
            work_queue_name=queue_name,
        )
    elif queue_name == _PREDICT_QUEUE:
        deployment_name = "predict-job-batch-deployment"
        deployment = await predict_job.ato_deployment(
            name=deployment_name,
            description="Prediction runtime deployment for predict-job flow (managed by delegated worker)",
            work_pool_name=pool_name,
            work_queue_name=queue_name,
        )

    if deployment is None:
        raise RuntimeError(
            f"Unsupported WORK_QUEUE_NAME '{queue_name}'. Expected one of: {_GPU_QUEUE}, {_DSPY_QUEUE}, {_PREDICT_QUEUE}."
        )

    await deployment.aapply(work_pool_name=pool_name)
    deployment_id = await client.resolve_deployment_id(deployment_name)
    if deployment_id is not None:
        await client._request(
            "PATCH",
            f"/deployments/{deployment_id}",
            json={"entrypoint": _FLOW_ENTRYPOINT, "path": _DEPLOYMENT_ROOT},
            expect_json=False,
            resource_label="deployment",
        )


async def main() -> None:
    # Each flow gets a well-known deployment name.
    # UI-created schedules that use this deployment name will be executed.
    drain_deploy = await drain_dataset.ato_deployment(
        name="drain-dataset-deployment",
        description="Default deployment for drain-dataset flow (managed by flow-worker)",
    )
    train_deploy = await train_job.ato_deployment(
        name="train-job-deployment",
        description="Default deployment for train-job flow (managed by flow-worker)",
    )
    predict_deploy = await predict_job.ato_deployment(
        name="predict-job-deployment",
        description="Default deployment for predict-job flow (managed by flow-worker)",
    )
    train_torch_deploy = await train_job.ato_deployment(
        name="train-job-torch-deployment",
        description="Torch runtime deployment for train-job flow (managed by flow-worker)",
        work_queue_name="train-gpu",
    )
    train_dspy_deploy = await train_job.ato_deployment(
        name="train-job-dspy-deployment",
        description="DSPy runtime deployment for train-job flow (managed by flow-worker)",
        work_queue_name="optimize-llm-cpu",
    )
    predict_queue_deploy = await predict_job.ato_deployment(
        name="predict-job-batch-deployment",
        description="Prediction runtime deployment for predict-job flow (managed by flow-worker)",
        work_queue_name="predict-batch",
    )
    # Use Runner for async context instead of serve()
    runner = Runner(name="flow-worker")
    await runner.aadd_deployment(drain_deploy)
    await runner.aadd_deployment(train_deploy)
    await runner.aadd_deployment(predict_deploy)
    await runner.aadd_deployment(train_torch_deploy)
    await runner.aadd_deployment(train_dspy_deploy)
    await runner.aadd_deployment(predict_queue_deploy)
    cfg = load_config()
    client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))
    for deployment_name, entrypoint in (
        ("drain-dataset-deployment", _DRAIN_ENTRYPOINT),
        ("train-job-deployment", _FLOW_ENTRYPOINT),
        ("predict-job-deployment", _PREDICT_ENTRYPOINT),
        ("predict-job-batch-deployment", _PREDICT_ENTRYPOINT),
        ("train-job-torch-deployment", _FLOW_ENTRYPOINT),
        ("train-job-dspy-deployment", _FLOW_ENTRYPOINT),
    ):
        deployment_id = await client.resolve_deployment_id(deployment_name)
        if deployment_id is not None:
            await client._request(
                "PATCH",
                f"/deployments/{deployment_id}",
                json={"entrypoint": entrypoint, "path": _DEPLOYMENT_ROOT},
                expect_json=False,
                resource_label="deployment",
            )
    await runner.start()


async def main_v2() -> None:
    """Bootstrap the owned deployment and start a Prefect process worker.

    The worker subprocess inherits the current Python environment so all
    flows (``train_job``, ``drain_dataset``) are importable.
    """
    pool_name = os.getenv("WORK_POOL_NAME", "training-pool")
    queue_name = os.getenv("WORK_QUEUE_NAME")
    if not queue_name:
        raise RuntimeError("WORK_QUEUE_NAME must be set for delegated worker mode")

    await _bootstrap_worker_deployment(pool_name=pool_name, queue_name=queue_name)

    cmd = [
        sys.executable, "-m", "prefect", "worker", "start",
        "--pool", pool_name,
        "--type", "process",
        "--work-queue", queue_name,
    ]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        check=False,
    )
    sys.exit(proc.returncode)


if __name__ == "__main__":
    mode = os.getenv("WORKER_MODE", "v1").lower()
    if mode == "v2":
        asyncio.run(main_v2())
    else:
        asyncio.run(main())
