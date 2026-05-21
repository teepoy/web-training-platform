from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.modules.sensors.application.services.sensor_dispatch import (
    SensorDispatchService,
)
from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.modules.sensors.domain.repository import SensorRepository
from app.shared.domain.protocols import PrefectClient


def get_sensor_repository(request: Request) -> SensorRepository:
    return request.app.state.container.sensor_repository


def get_prefect_client(request: Request) -> PrefectClient:
    return request.app.state.container.prefect_client


def get_sensor_registry(request: Request) -> SensorRegistry:
    return request.app.state.container.sensor_registry


def get_sensor_dispatch_service(
    repo: Annotated[SensorRepository, Depends(get_sensor_repository)],
    prefect_client: Annotated[PrefectClient, Depends(get_prefect_client)],
) -> SensorDispatchService:
    return SensorDispatchService(repository=repo, prefect_client=prefect_client)
