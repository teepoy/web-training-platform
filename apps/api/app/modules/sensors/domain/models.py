from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SensorSubscription(BaseModel):
    id: str
    sensor_id: str
    workflow_type: str
    filter_config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SensorCheckpoint(BaseModel):
    sensor_id: str
    watermark: dict[str, Any]
    updated_at: datetime


class SensorEvent(BaseModel):
    sensor_id: str
    payload: dict[str, Any]


class SensorEventBatch(BaseModel):
    sensor_id: str
    events: list[dict[str, Any]]
    watermark: dict[str, Any]
