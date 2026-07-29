from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.jobs.sensors.app.services.sensor_dispatch import (
    SensorDispatchService,
)
from app.modules.jobs.sensors.domain.entities.registry import SensorRegistry
from app.modules.jobs.sensors.domain.repository import SensorRepository
from app.shared.domain.protocols import PrefectClient
from app.shared.injection import resolve


def get_sensor_repository(request: Request) -> SensorRepository:
    return resolve(request, SensorRepository)


def get_prefect_client(request: Request) -> PrefectClient:
    return resolve(request, PrefectClient)


def get_sensor_registry(request: Request) -> SensorRegistry:
    return resolve(request, SensorRegistry)


def get_sensor_dispatch_service(
    repo: Annotated[SensorRepository, Depends(get_sensor_repository)],
    prefect_client: Annotated[PrefectClient, Depends(get_prefect_client)],
) -> SensorDispatchService:
    return SensorDispatchService(repository=repo, prefect_client=prefect_client)
