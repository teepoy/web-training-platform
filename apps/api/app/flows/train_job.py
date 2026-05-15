"""Training flow definition for Prefect work pool execution.

In V2, this Prefect flow delegates GPU training to the GPU worker HTTP API
instead of running the training pipeline in-process.  The Prefect worker
remains CPU-only — it submits the job, polls for completion, and relays
artifacts back to the orchestrator via the flow return value.
"""
from __future__ import annotations

import asyncio
import os
from logging import Logger

from prefect import flow, get_run_logger

from app.container import Container
from app.services.gpu_worker import GpuWorkerUnavailableError


async def _run_train_job(
    job_id: str,
    dataset_id: str,
    preset_id: str,
    created_by: str,
    logger: Logger,
) -> dict:
    """Submit training to GPU worker and poll until terminal state.

    On success returns ``{"status": "completed", "artifacts": [...], "metrics": {...}}``.
    On GPU-side failure or timeout raises an exception so Prefect marks the
    flow run as FAILED (the orchestrator picks this up as ``status: failed``).
    """
    container = Container()  # type: ignore[call-arg]
    gpu_worker = container.gpu_worker()

    submit_result = await gpu_worker.submit_train(
        platform_job_id=job_id,
        preset_id=preset_id,
        dataset_id=dataset_id,
    )
    gpu_job_id: str = submit_result["job_id"]
    logger.info("GPU job submitted: gpu_job_id=%s platform_job_id=%s", gpu_job_id, job_id)

    poll_interval = int(os.environ.get("GPU_WORKER_POLL_INTERVAL", "5"))
    max_poll_seconds = int(os.environ.get("GPU_WORKER_MAX_POLL_SECONDS", "7200"))
    elapsed = 0
    prev_status: str | None = None

    while True:
        status_response = await gpu_worker.get_train_status(gpu_job_id)
        current_status: str = status_response.get("status", "")

        if current_status != prev_status:
            logger.info(
                "GPU job %s status: %s → %s (elapsed=%ds)",
                gpu_job_id,
                prev_status or "submitted",
                current_status,
                elapsed,
            )
            prev_status = current_status

        if current_status == "completed":
            logger.info("GPU job %s completed successfully", gpu_job_id)
            artifacts = status_response.get("artifacts", [])
            if not isinstance(artifacts, list):
                artifacts = []
            metrics = status_response.get("metrics", {})
            return {
                "status": "completed",
                "artifacts": artifacts,
                "metrics": metrics,
            }

        if current_status in ("failed", "cancelled"):
            error_msg = status_response.get("error", f"GPU training {current_status}")
            logger.error("GPU job %s %s: %s", gpu_job_id, current_status, error_msg)
            raise RuntimeError(f"GPU training {current_status}: {error_msg}")

        if elapsed >= max_poll_seconds:
            logger.error(
                "GPU job %s timed out after %ds (max_poll_seconds=%d)",
                gpu_job_id,
                elapsed,
                max_poll_seconds,
            )
            raise TimeoutError(
                f"GPU training timed out after {max_poll_seconds}s for gpu_job_id={gpu_job_id}"
            )

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval


@flow(name="train-job")
async def train_job(
    job_id: str,
    dataset_id: str,
    preset_id: str,
    created_by: str = "system",
) -> dict:
    logger = get_run_logger()
    logger.info(
        "Starting train-job: job_id=%s dataset_id=%s preset_id=%s created_by=%s",
        job_id,
        dataset_id,
        preset_id,
        created_by,
    )

    try:
        result = await _run_train_job(
            job_id=job_id,
            dataset_id=dataset_id,
            preset_id=preset_id,
            created_by=created_by,
            logger=logger,
        )
    except GpuWorkerUnavailableError as exc:
        logger.error(
            "GPU worker unavailable for job_id=%s: %s — marking platform job as failed",
            job_id,
            exc,
        )
        raise
    except Exception as exc:
        logger.error("Training failed for job_id=%s: %s", job_id, exc)
        raise

    artifacts = result.get("artifacts", []) if isinstance(result.get("artifacts", []), list) else []
    logger.info("Training complete: artifacts=%s", len(artifacts))
    return result
