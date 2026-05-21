"""Prefect flow worker serve logic.

Flow definitions live in module-owned infrastructure packages.  This module
keeps the worker entrypoint logic centralized for deployment specs.
"""

from __future__ import annotations
# pyright: reportMissingImports=false

import asyncio
import os
import subprocess
import sys
from typing import Any

from prefect.runner import Runner
from prefect.schedules import Cron

from app.core.config import load_config
from app.modules.sensors.infrastructure.flows.dataset_size_sensor import (
    dataset_size_sensor,
)
from app.modules.sensors.infrastructure.flows.timer_sensor import timer_sensor
from app.modules.datasets.infrastructure.flows.drain_dataset import drain_dataset
from app.modules.prediction.infrastructure.flows.predict_job import predict_job
from app.modules.training.infrastructure.flows.train_job import train_job
from app.shared.infrastructure.prefect.client import PrefectClient

# GPU queues (train-gpu, predict-batch, embed-batch) are retired in V2.
# GPU workloads now route through the GPU worker HTTP API instead of Prefect queues.
# Only CPU-bound queues remain for the Prefect worker.
_DSPY_QUEUE = "optimize-llm-cpu"
_DEPLOYMENT_ROOT = "/app/apps/api"
_FLOW_ENTRYPOINT = "app/modules/training/infrastructure/flows/train_job.py:train_job"
_DRAIN_ENTRYPOINT = (
    "app/modules/datasets/infrastructure/flows/drain_dataset.py:drain_dataset"
)
_PREDICT_ENTRYPOINT = (
    "app/modules/prediction/infrastructure/flows/predict_job.py:predict_job"
)
_SENSOR_ENTRYPOINT = "app/modules/sensors/infrastructure/flows/dataset_size_sensor.py:dataset_size_sensor"
_TIMER_ENTRYPOINT = (
    "app/modules/sensors/infrastructure/flows/timer_sensor.py:timer_sensor"
)

_QUEUE_POOLS = {
    _DSPY_QUEUE: "default-pool",
}


def _deployment_entrypoint(deployment_name: str) -> str:
    if deployment_name == "drain-dataset-deployment":
        return _DRAIN_ENTRYPOINT
    if deployment_name == "dataset-size-sensor-deployment":
        return _SENSOR_ENTRYPOINT
    if deployment_name == "timer-sensor-deployment":
        return _TIMER_ENTRYPOINT
    if deployment_name in {
        "predict-job-deployment",
        "predict-job-batch-deployment",
        "embed-job-batch-deployment",
    }:
        return _PREDICT_ENTRYPOINT
    return _FLOW_ENTRYPOINT


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

    effective_pool_name = _QUEUE_POOLS.get(queue_name, pool_name)
    await _ensure_work_pool(effective_pool_name)
    cfg = load_config()
    client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))

    if queue_name == _DSPY_QUEUE:
        deployment_name = "train-job-dspy-deployment"
        deployment = await train_job.ato_deployment(
            name=deployment_name,
            description="DSPy runtime deployment for train-job flow (managed by delegated worker)",
            work_pool_name=effective_pool_name,
            work_queue_name=queue_name,
        )

    if deployment is None:
        raise RuntimeError(
            f"Unsupported WORK_QUEUE_NAME '{queue_name}'. Expected: {_DSPY_QUEUE}."
        )

    await deployment.aapply(work_pool_name=effective_pool_name)
    deployment_id = await client.resolve_deployment_id(deployment_name)
    if deployment_id is not None:
        await client._request(
            "PATCH",
            f"/deployments/{deployment_id}",
            json={
                "entrypoint": _deployment_entrypoint(deployment_name),
                "path": _DEPLOYMENT_ROOT,
            },
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
    sensor_deploy = await dataset_size_sensor.ato_deployment(
        name="dataset-size-sensor-deployment",
        description="Polls dataset sizes and emits events (managed by flow-worker)",
        schedules=[Cron("*/5 * * * *")],
    )
    timer_deploy = await timer_sensor.ato_deployment(
        name="timer-sensor-deployment",
        description="Emits timestamped events on a configurable schedule (managed by flow-worker)",
        schedules=[Cron("* * * * *")],
    )
    runner = Runner(name="flow-worker")
    await runner.aadd_deployment(drain_deploy)
    await runner.aadd_deployment(train_deploy)
    await runner.aadd_deployment(predict_deploy)
    await runner.aadd_deployment(train_torch_deploy)
    await runner.aadd_deployment(train_dspy_deploy)
    await runner.aadd_deployment(predict_queue_deploy)
    await runner.aadd_deployment(sensor_deploy)
    await runner.aadd_deployment(timer_deploy)
    cfg = load_config()
    client = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))
    for deployment_name, entrypoint in (
        (
            "drain-dataset-deployment",
            _deployment_entrypoint("drain-dataset-deployment"),
        ),
        (
            "dataset-size-sensor-deployment",
            _deployment_entrypoint("dataset-size-sensor-deployment"),
        ),
        (
            "timer-sensor-deployment",
            _deployment_entrypoint("timer-sensor-deployment"),
        ),
        ("train-job-deployment", _deployment_entrypoint("train-job-deployment")),
        ("predict-job-deployment", _deployment_entrypoint("predict-job-deployment")),
        (
            "predict-job-batch-deployment",
            _deployment_entrypoint("predict-job-batch-deployment"),
        ),
        (
            "train-job-torch-deployment",
            _deployment_entrypoint("train-job-torch-deployment"),
        ),
        (
            "train-job-dspy-deployment",
            _deployment_entrypoint("train-job-dspy-deployment"),
        ),
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
    """Bootstrap the owned deployment and start a Prefect process worker."""
    pool_name = os.getenv("WORK_POOL_NAME", "default-pool")
    queue_name = os.getenv("WORK_QUEUE_NAME")
    if not queue_name:
        raise RuntimeError("WORK_QUEUE_NAME must be set for delegated worker mode")

    await _bootstrap_worker_deployment(pool_name=pool_name, queue_name=queue_name)

    cmd = [
        sys.executable,
        "-m",
        "prefect",
        "worker",
        "start",
        "--pool",
        pool_name,
        "--type",
        "process",
        "--work-queue",
        queue_name,
    ]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        check=False,
    )
    sys.exit(proc.returncode)
