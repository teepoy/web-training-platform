from __future__ import annotations

from pathlib import Path

from app.modules.sensors.domain.entities.registry import SensorRegistry
from app.modules.sensors.domain.entities.schema import SensorDefinition


SENSORS_DIR = Path(__file__).resolve().parents[1] / "sensors"


def _loaded_registry() -> SensorRegistry:
    registry = SensorRegistry(sensors_dir=SENSORS_DIR, strict=True)
    loaded = registry.load()
    assert loaded > 0
    return registry


def test_registry_loads_yaml_files_as_sensor_definitions() -> None:
    registry = _loaded_registry()

    sensors = registry.list_all()

    assert sensors
    assert all(isinstance(sensor, SensorDefinition) for sensor in sensors)


def test_get_returns_dataset_size_sensor_definition() -> None:
    registry = _loaded_registry()

    sensor = registry.get("dataset_size_sensor")

    assert sensor is not None
    assert sensor.id == "dataset_size_sensor"
    assert sensor.name == "Dataset Size Sensor"


def test_get_returns_none_for_unknown_sensor() -> None:
    registry = _loaded_registry()

    assert registry.get("nonexistent") is None


def test_list_all_returns_non_empty_list() -> None:
    registry = _loaded_registry()

    assert len(registry.list_all()) >= 1


def test_loaded_definition_includes_triggers_and_filter_schema() -> None:
    registry = _loaded_registry()

    sensor = registry.get("dataset_size_sensor")

    assert sensor is not None
    assert sensor.available_triggers
    assert "train" in sensor.available_triggers
    assert sensor.filter_schema
    assert "properties" in sensor.filter_schema
