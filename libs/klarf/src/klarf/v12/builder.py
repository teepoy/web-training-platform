from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Self

from klarf.errors import KlarfValidationError, UnsupportedKlarfVersionError
from klarf.models import KlarfScalar
from klarf.v12.models import (
    SUPPORTED_VERSIONS,
    TABLE_SCHEMA_NAMES,
    Klarf12CountedList,
    Klarf12Document,
    Klarf12Item,
    Klarf12Record,
    Klarf12Schema,
    Klarf12Table,
    Klarf12Value,
    Klarf12Version,
)


class Klarf12Builder:
    """Fluent builder for flat KLARF 1.1/1.2 documents."""

    def __init__(self, version: Klarf12Version) -> None:
        if version not in SUPPORTED_VERSIONS:
            rendered = ".".join(str(part) for part in version)
            raise UnsupportedKlarfVersionError(
                f"KLARF 1.2 builder does not support FileVersion {rendered}"
            )
        self._version = version
        self._items: list[Klarf12Item] = []
        self._schemas: dict[str, Klarf12Schema] = {}

    def add_record(self, name: str, *values: KlarfScalar) -> Self:
        self._items.append(Klarf12Record(name=name, values=tuple(values)))
        return self

    def add_counted_list(
        self,
        name: str,
        *,
        rows: Iterable[Sequence[KlarfScalar]],
    ) -> Self:
        self._items.append(
            Klarf12CountedList(
                name=name,
                rows=tuple(tuple(row) for row in rows),
            )
        )
        return self

    def add_schema(self, name: str, *columns: str) -> Self:
        schema = Klarf12Schema(name=name, columns=tuple(columns))
        self._schemas[name] = schema
        self._items.append(schema)
        return self

    def add_table(
        self,
        name: str,
        *,
        schema_name: str,
        rows: Iterable[Sequence[Klarf12Value]],
    ) -> Self:
        expected_schema = TABLE_SCHEMA_NAMES.get(name)
        if expected_schema is not None and schema_name != expected_schema:
            raise KlarfValidationError(
                f"KLARF 1.2 table {name!r} requires schema {expected_schema!r}, "
                f"got {schema_name!r}"
            )
        schema = self._schemas.get(schema_name)
        if schema is None:
            raise KlarfValidationError(
                f"KLARF 1.2 table {name!r} requires a preceding {schema_name!r}"
            )
        self._items.append(
            Klarf12Table(
                name=name,
                columns=schema.columns,
                rows=tuple(tuple(row) for row in rows),
            )
        )
        return self

    def build(self) -> Klarf12Document:
        return Klarf12Document(version=self._version, items=tuple(self._items))
