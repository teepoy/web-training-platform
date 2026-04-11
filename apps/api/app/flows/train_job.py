"""Training flow definition for Prefect work pool execution."""
from __future__ import annotations

from prefect import flow, get_run_logger, task

from app.runtime.training_runner import run_training_pipeline


@task(name="run-training")
async def run_training(job_id: str, dataset_id: str, preset_id: str) -> dict:
    return await run_training_pipeline(job_id=job_id, dataset_id=dataset_id, preset_id=preset_id)


@flow(name="train-job")
async def train_job(
    job_id: str,
    dataset_id: str,
    preset_id: str,
    created_by: str = "system",
) -> dict:
    logger = get_run_logger()
    logger.info(
        f"Starting train-job: job_id={job_id} dataset_id={dataset_id} "
        f"preset_id={preset_id} created_by={created_by}"
    )
    result = await run_training(job_id=job_id, dataset_id=dataset_id, preset_id=preset_id)
    artifacts = result.get("artifacts", []) if isinstance(result.get("artifacts", []), list) else []
    logger.info("Training complete: artifacts=%s", len(artifacts))
    return result
