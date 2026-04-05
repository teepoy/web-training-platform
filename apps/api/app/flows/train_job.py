"""Training flow definition for Prefect work pool execution.

This flow runs inside a Prefect worker process, NOT in the API context.
It receives job parameters and orchestrates the training pipeline as
discrete Prefect tasks.  Currently a scaffold — real training logic
will be added later.
"""
from __future__ import annotations

import asyncio
import os

from prefect import flow, get_run_logger, task

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")


@task(name="prepare-dataset")
async def prepare_dataset(job_id: str, dataset_id: str) -> dict:
    logger = get_run_logger()
    logger.info(f"Preparing dataset dataset_id={dataset_id} for job_id={job_id}")
    # Placeholder: simulate dataset loading
    await asyncio.sleep(0.5)
    logger.info(f"Dataset {dataset_id} loaded and validated")
    return {"dataset_id": dataset_id, "status": "prepared", "sample_count": 1000}


@task(name="run-training")
async def run_training(job_id: str, dataset_id: str, preset_id: str) -> dict:
    logger = get_run_logger()
    logger.info(f"Starting training job_id={job_id} preset_id={preset_id}")
    total_epochs = 5
    for epoch in range(1, total_epochs + 1):
        await asyncio.sleep(1.0)
        loss = round(1.0 / epoch, 4)
        logger.info(f"Epoch {epoch}/{total_epochs} complete — loss={loss}")
    logger.info(f"Training finished for job_id={job_id}")
    return {"job_id": job_id, "epochs": total_epochs, "final_loss": 0.2}


@task(name="save-artifacts")
async def save_artifacts(job_id: str) -> list[str]:
    logger = get_run_logger()
    logger.info(f"Saving artifacts for job_id={job_id}")
    await asyncio.sleep(0.3)
    artifact_uris = [
        f"s3://artifacts/{job_id}/model",
        f"s3://artifacts/{job_id}/metrics.json",
    ]
    logger.info(f"Artifacts saved: {artifact_uris}")
    return artifact_uris


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

    ds_result = await prepare_dataset(job_id, dataset_id)
    logger.info(f"Dataset prepared: {ds_result['sample_count']} samples")

    train_result = await run_training(job_id, dataset_id, preset_id)
    logger.info(f"Training complete: {train_result['epochs']} epochs, loss={train_result['final_loss']}")

    artifacts = await save_artifacts(job_id)
    logger.info(f"Artifacts persisted: {len(artifacts)} items")

    return {
        "job_id": job_id,
        "status": "completed",
        "artifacts": artifacts,
    }
