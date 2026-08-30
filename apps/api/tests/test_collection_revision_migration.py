from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/a2b3c4d5e6f7_collection_revisions_and_sc_partition.py"
    )
    spec = importlib.util.spec_from_file_location("collection_revision_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_rejects_legacy_recipe_partitions_before_schema_changes() -> None:
    migration = _migration_module()

    class Result:
        def all(self) -> list[tuple[str, int]]:
            return [("recipe_id", 2)]

    class Bind:
        def execute(self, _statement: object) -> Result:
            return Result()

    class Operations:
        def get_bind(self) -> Bind:
            return Bind()

        def batch_alter_table(self, _table: str) -> None:
            raise AssertionError("schema mutation started before compatibility check")

    setattr(migration, "op", Operations())

    with pytest.raises(RuntimeError, match="recipe_id.*remove or reassign"):
        migration.upgrade()
