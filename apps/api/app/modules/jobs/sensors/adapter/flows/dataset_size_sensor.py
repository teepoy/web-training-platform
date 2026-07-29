from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import TypedDict

import httpx
from prefect import flow, get_run_logger, task

from app.modules.jobs.sensors.adapter.flows.sensor_base import SENSOR_EVENTS_URL

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")


class DatasetSizeEvent(TypedDict):
    dataset_id: str
    sample_count: int


class DatasetRecord(TypedDict, total=False):
    id: str
    sample_count: int


@task(name="fetch-dataset-sizes")
async def fetch_dataset_sizes() -> list[DatasetSizeEvent]:
    logger = get_run_logger()
    url = f"{PLATFORM_API_URL}/api/v1/datasets"
    logger.info(f"Fetching dataset sizes from {url}")

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()

    datasets = response.json()
    events: list[DatasetSizeEvent] = []
    for dataset in datasets:
        record = DatasetRecord(dataset)
        dataset_id = record.get("id")
        if dataset_id is None:
            logger.warning(f"Skipping dataset without id: {dataset}")
            continue
        events.append(
            {
                "dataset_id": str(dataset_id),
                "sample_count": int(record.get("sample_count", 0)),
            }
        )

    logger.info(f"Fetched {len(events)} dataset size events")
    return events


@flow(name="dataset-size-sensor")
async def dataset_size_sensor() -> dict[str, object]:
    logger = get_run_logger()
    events = await fetch_dataset_sizes()
    checked_at = datetime.now(UTC).isoformat()
    payload = {
        "sensor_id": "dataset_size_sensor",
        "events": events,
        "watermark": {"checked_at": checked_at},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(SENSOR_EVENTS_URL, json=payload)
        response.raise_for_status()

    result = response.json()
    logger.info(
        f"Posted {len(events)} dataset size events to {SENSOR_EVENTS_URL}: "
        f"status={response.status_code}"
    )
    return {
        "event_count": len(events),
        "checked_at": checked_at,
        "result": result,
    }
