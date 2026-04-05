"""Flow worker entrypoint.

Run with:
    python -m app.flows.serve

This starts a long-lived process that polls Prefect server for scheduled runs.

V1 strategy
-----------
We use ``prefect.serve()`` to register and serve deployments for every flow
defined in this package.  On startup the worker:

1. Registers a default deployment per flow (``{flow_name}-deployment``) so
   at least one always exists.
2. Picks up scheduled/triggered runs for those deployments.

Deployments created through the platform UI (which hit the Prefect REST API
directly) will also appear on the server.  In V1, the worker only executes
runs for its own served deployments — this is a known limitation.  The UI
deployment names should match the served names to ensure execution.  V2 will
migrate to work pools for fully dynamic execution.

V2 strategy
-----------
A Prefect worker process is started via subprocess, pulling jobs from a
named work pool.  Flows (like ``train_job``) are imported so they are
registered in the Python environment the worker subprocess inherits.

Set ``WORKER_MODE=v2`` to activate this path.

Environment variables
---------------------
PREFECT_API_URL     — Prefect server URL (set by compose).
PLATFORM_API_URL    — Platform API URL for flow callbacks (e.g. ``http://api:8000``).
WORKER_MODE         — ``v1`` (default) or ``v2``.
WORK_POOL_NAME      — Work pool name for V2 mode (default ``training-pool``).
WORK_QUEUE_NAME     — Work queue name for V2 mode (default ``default``).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from prefect import serve

from app.flows.drain_dataset import drain_dataset
from app.flows.train_job import train_job  # noqa: F401 — register flow for V2 worker


async def main() -> None:
    # Each flow gets a well-known deployment name.
    # UI-created schedules that use this deployment name will be executed.
    drain_deploy = drain_dataset.to_deployment(
        name="drain-dataset-deployment",
        description="Default deployment for drain-dataset flow (managed by flow-worker)",
    )
    await serve(drain_deploy)


async def main_v2() -> None:
    """Start a Prefect process worker that pulls from a work pool.

    The worker subprocess inherits the current Python environment so all
    flows (``train_job``, ``drain_dataset``) are importable.
    """
    pool_name = os.getenv("WORK_POOL_NAME", "training-pool")
    queue_name = os.getenv("WORK_QUEUE_NAME", "default")
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
