from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.modules.jobs.sensors.domain.entities.schema import SensorDefinition

logger = logging.getLogger(__name__)


class SensorRegistryError(Exception):
    """Raised when a sensor file fails validation."""


class SensorRegistry:
    """In-memory registry of engineer-managed sensors."""

    def __init__(self, sensors_dir: str | Path, *, strict: bool = True) -> None:
        self._root = Path(sensors_dir)
        self._strict = strict
        self._sensors: dict[str, SensorDefinition] = {}

    def load(self) -> int:
        """Scan the sensor directory, parse and validate all sensors."""
        self._sensors.clear()

        if not self._root.is_dir():
            msg = f"Sensors directory does not exist: {self._root}"
            if self._strict:
                raise SensorRegistryError(msg)
            logger.warning(msg)
            return 0

        loaded = 0
        for sensor_file in sorted(self._root.glob("*.yaml")):
            try:
                definition = self._load_single(sensor_file)
                if definition.id in self._sensors:
                    raise SensorRegistryError(
                        f"Duplicate sensor id '{definition.id}' in {sensor_file}"
                    )
                self._sensors[definition.id] = definition
                loaded += 1
                logger.info("Loaded sensor '%s' from %s", definition.id, sensor_file)
            except Exception as exc:
                if self._strict:
                    raise SensorRegistryError(
                        f"Failed to load {sensor_file}: {exc}"
                    ) from exc
                logger.warning("Skipping invalid sensor %s: %s", sensor_file, exc)

        logger.info("Sensor registry loaded: %d sensors from %s", loaded, self._root)
        return loaded

    def get(self, sensor_id: str) -> SensorDefinition | None:
        """Return a single sensor by ID, or None if not found."""
        return self._sensors.get(sensor_id)

    def list_all(self) -> list[SensorDefinition]:
        """Return all loaded sensors."""
        return list(self._sensors.values())

    @property
    def count(self) -> int:
        return len(self._sensors)

    def _load_single(self, sensor_file: Path) -> SensorDefinition:
        raw = yaml.safe_load(sensor_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SensorRegistryError(f"Expected a YAML mapping in {sensor_file}")
        return SensorDefinition(**raw)
