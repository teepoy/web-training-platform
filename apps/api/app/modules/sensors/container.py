from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.modules.sensors.adapter.repositories.repository import SensorRepositoryImpl
from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.shared.context import SharedInfra


@dataclass
class SensorsContext:
    sensor_registry: SensorRegistry
    sensor_repository: SensorRepositoryImpl


def init_sensors(shared: SharedInfra) -> SensorsContext:
    cfg = shared.config
    sensors_dir = (
        str(Path(cfg.data.dir) / cfg.sensors.dir)
        if cfg.data.dir
        else str(cfg.sensors.dir)
    )
    registry = SensorRegistry(
        sensors_dir=sensors_dir,
        strict=bool(cfg.sensors.strict),
    )
    repo = SensorRepositoryImpl(session_factory=shared.session_factory)
    return SensorsContext(sensor_registry=registry, sensor_repository=repo)
