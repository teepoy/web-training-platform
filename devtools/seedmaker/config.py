from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FixtureConfig:
    """Dataset metadata used by deterministic test-data builders."""

    name: str
    dataset_name: str = ""
    description: str = ""
    label_space: list[str] = field(default_factory=list)
    dataset_type: str = "image_sc"
    task_type: str = "patch"
    metadata_schema: dict[str, object] = field(default_factory=dict)
    storage_mode: str = "db_full"
