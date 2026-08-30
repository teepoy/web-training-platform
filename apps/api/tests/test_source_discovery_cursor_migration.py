from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/b3c4d5e6f7a8_source_discovery_publication_cursor.py"
    )
    spec = importlib.util.spec_from_file_location(
        "source_discovery_cursor_migration", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_rejects_collapsed_source_identity_before_schema_changes() -> None:
    migration = _migration_module()

    class Result:
        def __init__(self, duplicate: bool) -> None:
            self._duplicate = duplicate

        def first(self) -> tuple[int] | None:
            return (1,) if self._duplicate else None

    class Bind:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, _statement: object) -> Result:
            self.calls += 1
            return Result(self.calls == 1)

    class Operations:
        def get_bind(self) -> Bind:
            return Bind()

        def drop_table(self, _table: str) -> None:
            raise AssertionError("schema mutation started before identity check")

    setattr(migration, "op", Operations())

    with pytest.raises(RuntimeError, match="source_version.*before upgrading"):
        migration.upgrade()
