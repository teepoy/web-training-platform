from __future__ import annotations

import os

import httpx
from prefect import flow, get_run_logger, task

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")


@task(name="export-dataset")
async def export_dataset_task(
    dataset_id: str,
    target_format: str,
    destination: str,
) -> dict:
    logger = get_run_logger()
    logger.info(
        f"Exporting dataset_id={dataset_id} as format={target_format} to destination={destination}"
    )

    url = f"{PLATFORM_API_URL}/api/v1/exports/{dataset_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()

    logger.info(f"Export request completed for dataset_id={dataset_id}: status={response.status_code}")

    return {
        "dataset_id": dataset_id,
        "format": target_format,
        "destination": destination,
        "status": "exported",
    }


@flow(name="drain-dataset")
async def drain_dataset(
    dataset_id: str,
    target_format: str = "jsonl",
    destination: str = "local",
) -> dict:
    logger = get_run_logger()
    logger.info(f"Starting drain-dataset: dataset_id={dataset_id}")

    result = await export_dataset_task(dataset_id, target_format, destination)
    return result
