from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.modules.jobs.sensors.port.http.deps import (
    get_sensor_dispatch_service,
    get_sensor_repository,
)
from app.modules.jobs.sensors.app.services.sensor_dispatch import (
    SensorDispatchService,
)
from app.modules.jobs.sensors.domain.entities.registry import SensorRegistry
from app.modules.jobs.sensors.domain.repository import SensorRepository
from app.modules.jobs.sensors.port.http.deps import get_sensor_registry

router = APIRouter(prefix="/api/v1", tags=["sensors"])


class CreateSubscriptionRequest(BaseModel):
    workflow_type: str
    filter_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class UpdateSubscriptionRequest(BaseModel):
    filter_config: dict[str, Any] | None = None
    enabled: bool | None = None


class SensorEventBatch(BaseModel):
    sensor_id: str
    events: list[dict[str, Any]]
    watermark: dict[str, Any] | None = None


class SensorDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    cron: str
    filter_schema: dict[str, Any]
    available_triggers: list[str]


class SensorSubscriptionResponse(BaseModel):
    id: str
    sensor_id: str
    workflow_type: str
    filter_config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SensorEventIngestResponse(BaseModel):
    dispatched: int
    triggered: int
    errors: int


@router.get("/sensors", response_model=list[SensorDefinitionResponse])
async def list_sensors(
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
) -> list[SensorDefinitionResponse]:
    return [
        SensorDefinitionResponse(**sensor.model_dump())
        for sensor in sensor_registry.list_all()
    ]


@router.get(
    "/sensors/{sensor_id}/subscriptions",
    response_model=list[SensorSubscriptionResponse],
)
async def list_sensor_subscriptions(
    sensor_id: str,
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
    sensor_repository: Annotated[SensorRepository, Depends(get_sensor_repository)],
) -> list[SensorSubscriptionResponse]:
    _get_sensor_or_404(sensor_registry, sensor_id)
    subscriptions = await sensor_repository.list_subscriptions(sensor_id)
    return [
        SensorSubscriptionResponse(**subscription.model_dump())
        for subscription in subscriptions
    ]


@router.post(
    "/sensors/{sensor_id}/subscriptions",
    response_model=SensorSubscriptionResponse,
)
async def create_sensor_subscription(
    sensor_id: str,
    payload: CreateSubscriptionRequest,
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
    sensor_repository: Annotated[SensorRepository, Depends(get_sensor_repository)],
) -> SensorSubscriptionResponse:
    sensor = _get_sensor_or_404(sensor_registry, sensor_id)
    if payload.workflow_type not in sensor.available_triggers:
        raise HTTPException(
            status_code=422,
            detail="workflow_type is not available for this sensor",
        )
    subscription = await sensor_repository.create_subscription(
        sensor_id=sensor_id,
        workflow_type=payload.workflow_type,
        filter_config=payload.filter_config,
        enabled=payload.enabled,
    )
    return SensorSubscriptionResponse(**subscription.model_dump())


@router.patch(
    "/sensors/{sensor_id}/subscriptions/{sub_id}",
    response_model=SensorSubscriptionResponse,
)
async def update_sensor_subscription(
    sensor_id: str,
    sub_id: str,
    payload: UpdateSubscriptionRequest,
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
    sensor_repository: Annotated[SensorRepository, Depends(get_sensor_repository)],
) -> SensorSubscriptionResponse:
    _get_sensor_or_404(sensor_registry, sensor_id)
    existing = await sensor_repository.get_subscription(sub_id)
    if existing is None or existing.sensor_id != sensor_id:
        raise HTTPException(status_code=404, detail="sensor subscription not found")
    subscription = await sensor_repository.update_subscription(
        sub_id,
        filter_config=payload.filter_config,
        enabled=payload.enabled,
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="sensor subscription not found")
    return SensorSubscriptionResponse(**subscription.model_dump())


@router.delete("/sensors/{sensor_id}/subscriptions/{sub_id}")
async def delete_sensor_subscription(
    sensor_id: str,
    sub_id: str,
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
    sensor_repository: Annotated[SensorRepository, Depends(get_sensor_repository)],
) -> dict[str, bool]:
    _get_sensor_or_404(sensor_registry, sensor_id)
    existing = await sensor_repository.get_subscription(sub_id)
    if existing is None or existing.sensor_id != sensor_id:
        raise HTTPException(status_code=404, detail="sensor subscription not found")
    deleted = await sensor_repository.delete_subscription(sub_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="sensor subscription not found")
    return {"deleted": True}


@router.post("/sensors/events", response_model=SensorEventIngestResponse)
async def ingest_sensor_events(
    batch: SensorEventBatch,
    sensor_registry: Annotated[SensorRegistry, Depends(get_sensor_registry)],
    sensor_repository: Annotated[SensorRepository, Depends(get_sensor_repository)],
    sensor_dispatch: Annotated[
        SensorDispatchService,
        Depends(get_sensor_dispatch_service),
    ],
) -> SensorEventIngestResponse:
    _get_sensor_or_404(sensor_registry, batch.sensor_id)
    summary = await sensor_dispatch.dispatch(batch.sensor_id, batch.events)
    if batch.watermark is not None:
        await sensor_repository.upsert_checkpoint(batch.sensor_id, batch.watermark)
    return SensorEventIngestResponse(
        dispatched=summary.matched,
        triggered=summary.triggered,
        errors=summary.errors,
    )


def _get_sensor_or_404(sensor_registry: SensorRegistry, sensor_id: str) -> Any:
    sensor = sensor_registry.get(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    return sensor
