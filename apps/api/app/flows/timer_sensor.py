from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import httpx
from prefect import flow, get_run_logger

from app.flows.sensor_base import SENSOR_EVENTS_URL


class TimerEvent(TypedDict):
    timestamp: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    weekday: int


@flow(name="timer-sensor")
async def timer_sensor() -> dict[str, object]:
    """Emit a single timestamped event on each scheduled tick.

    A minimal example sensor that emits the current datetime components
    as a sensor event. Subscriptions can filter on any time component
    (year, month, day, hour, minute, weekday).
    """
    logger = get_run_logger()
    now = datetime.now(UTC)
    event: TimerEvent = {
        "timestamp": now.isoformat(),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
        "second": now.second,
        "weekday": now.weekday(),
    }
    logger.info(f"Timer sensor tick: {event['timestamp']}")

    payload = {
        "sensor_id": "timer_sensor",
        "events": [event],
        "watermark": {"last_tick": event["timestamp"]},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(SENSOR_EVENTS_URL, json=payload)
        response.raise_for_status()

    result = response.json()
    logger.info(
        f"Posted timer event to {SENSOR_EVENTS_URL}: status={response.status_code}"
    )
    return {
        "event": event,
        "checked_at": event["timestamp"],
        "result": result,
    }
