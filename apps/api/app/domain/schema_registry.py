from __future__ import annotations

from app.domain.dataset_schema import DatasetSchema
from app.domain.types import DatasetType, TaskType


_registry: dict[str, DatasetSchema] = {}


def register(schema: DatasetSchema) -> None:
    """Register a schema descriptor keyed by its ``dataset_type``."""
    _registry[schema.dataset_type] = schema


def get(dataset_type: str) -> DatasetSchema | None:
    """Return the schema for *dataset_type*, or ``None`` if not registered."""
    return _registry.get(dataset_type)


def get_allowed_pairs() -> dict[DatasetType, TaskType]:
    """Return a mapping of all registered dataset→task type pairs.

    Replaces the hand-maintained ``ALLOWED_DATASET_TASK_PAIRS`` dict in
    ``services/compatibility.py``.
    """
    result: dict[DatasetType, TaskType] = {}
    for schema in _registry.values():
        try:
            dt = DatasetType(schema.dataset_type)
            tt = TaskType(schema.task_type)
            result[dt] = tt
        except ValueError:
            # Schema registered before enum values were added; skip gracefully.
            pass
    return result


def list_all() -> list[DatasetSchema]:
    """Return all registered schemas in insertion order."""
    return list(_registry.values())
