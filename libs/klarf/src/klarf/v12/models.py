from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from klarf.errors import KlarfValidationError, UnsupportedKlarfVersionError
from klarf.models import KlarfScalar, _validate_name, _validate_scalar

Klarf12Version: TypeAlias = tuple[int, int]
SUPPORTED_VERSIONS: frozenset[Klarf12Version] = frozenset({(1, 1), (1, 2)})

TABLE_SCHEMA_NAMES = {
    "DefectList": "DefectRecordSpec",
    "SummaryList": "SummarySpec",
}

COUNTED_LIST_WIDTHS = {
    "ClassLookup": 2,
    "CustomWaferList": 2,
    "ProcessEquipmentIDList": 1,
    "RemovedDieList": 2,
    "SampleDieMap": 2,
    "SampleTestPlan": 2,
}


@dataclass(frozen=True, slots=True)
class Klarf12ImageList:
    """The variable-width value encoded by a KLARF 1.2 ``IMAGELIST`` column."""

    items: tuple[tuple[KlarfScalar, KlarfScalar], ...]

    def __post_init__(self) -> None:
        for item in self.items:
            if len(item) != 2:
                raise KlarfValidationError(
                    "KLARF 1.2 image-list entries must contain exactly two values"
                )
            for value in item:
                _validate_scalar(value)


Klarf12Value: TypeAlias = KlarfScalar | Klarf12ImageList


@dataclass(frozen=True, slots=True)
class Klarf12Record:
    """A semicolon-terminated, non-tabular KLARF 1.2 record."""

    name: str
    values: tuple[KlarfScalar, ...] = ()

    def __post_init__(self) -> None:
        _validate_name(self.name, role="KLARF 1.2 record name")
        if self.name in {"FileVersion", "EndOfFile"}:
            raise KlarfValidationError(
                f"{self.name} is owned by Klarf12Document and cannot be an item"
            )
        for value in self.values:
            _validate_scalar(value)


@dataclass(frozen=True, slots=True)
class Klarf12Schema:
    """A counted ``*Spec`` record describing a following table."""

    name: str
    columns: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="KLARF 1.2 schema name")
        for column in self.columns:
            _validate_name(column, role="KLARF 1.2 schema column")
        if len(self.columns) != len(set(self.columns)):
            raise KlarfValidationError(
                f"KLARF 1.2 schema {self.name!r} contains duplicate columns"
            )


@dataclass(frozen=True, slots=True)
class Klarf12Table:
    """Rows interpreted using a preceding KLARF 1.2 schema record."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Klarf12Value, ...], ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="KLARF 1.2 table name")
        for column in self.columns:
            _validate_name(column, role="KLARF 1.2 table column")
        if len(self.columns) != len(set(self.columns)):
            raise KlarfValidationError(
                f"KLARF 1.2 table {self.name!r} contains duplicate columns"
            )
        for row_number, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise KlarfValidationError(
                    f"KLARF 1.2 table {self.name!r} row {row_number} has "
                    f"{len(row)} values; expected {len(self.columns)}"
                )
            for value in row:
                if isinstance(value, Klarf12ImageList):
                    continue
                _validate_scalar(value)
            normalized_columns = tuple(column.upper() for column in self.columns)
            if "IMAGELIST" not in normalized_columns:
                continue
            image_list_index = normalized_columns.index("IMAGELIST")
            image_list = row[image_list_index]
            if not isinstance(image_list, Klarf12ImageList):
                raise KlarfValidationError(
                    f"KLARF 1.2 table {self.name!r} row {row_number} IMAGELIST "
                    "must be a Klarf12ImageList"
                )
            if "IMAGECOUNT" not in normalized_columns:
                continue
            image_count = row[normalized_columns.index("IMAGECOUNT")]
            if (
                isinstance(image_count, bool)
                or not isinstance(image_count, int)
                or image_count < 0
            ):
                raise KlarfValidationError(
                    f"KLARF 1.2 table {self.name!r} row {row_number} IMAGECOUNT "
                    "must be a non-negative integer"
                )
            if image_count != len(image_list.items):
                raise KlarfValidationError(
                    f"KLARF 1.2 table {self.name!r} row {row_number} IMAGECOUNT "
                    f"is {image_count} but IMAGELIST contains "
                    f"{len(image_list.items)} items"
                )

    def as_dicts(self) -> tuple[dict[str, Klarf12Value], ...]:
        return tuple(dict(zip(self.columns, row, strict=True)) for row in self.rows)


@dataclass(frozen=True, slots=True)
class Klarf12CountedList:
    """A counted flat list such as ``ClassLookup`` or ``SampleTestPlan``."""

    name: str
    rows: tuple[tuple[KlarfScalar, ...], ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="KLARF 1.2 counted-list name")
        expected_width = COUNTED_LIST_WIDTHS.get(self.name)
        inferred_width = (
            expected_width
            if expected_width is not None
            else len(self.rows[0])
            if self.rows
            else None
        )
        for row_number, row in enumerate(self.rows, start=1):
            if not row:
                raise KlarfValidationError(
                    f"KLARF 1.2 counted list {self.name!r} row {row_number} is empty"
                )
            if inferred_width is not None and len(row) != inferred_width:
                raise KlarfValidationError(
                    f"KLARF 1.2 counted list {self.name!r} row {row_number} has "
                    f"{len(row)} values; expected {inferred_width}"
                )
            for value in row:
                _validate_scalar(value)


Klarf12Item: TypeAlias = (
    Klarf12Record | Klarf12Schema | Klarf12Table | Klarf12CountedList
)


@dataclass(frozen=True, slots=True)
class Klarf12Document:
    version: Klarf12Version
    items: tuple[Klarf12Item, ...] = ()

    def __post_init__(self) -> None:
        if self.version not in SUPPORTED_VERSIONS:
            rendered = ".".join(str(part) for part in self.version)
            raise UnsupportedKlarfVersionError(
                f"KLARF 1.2 parser/writer does not support FileVersion {rendered}"
            )

        schemas: dict[str, Klarf12Schema] = {}
        for item in self.items:
            if isinstance(item, Klarf12Schema):
                schemas[item.name] = item
                continue
            if not isinstance(item, Klarf12Table):
                continue
            schema_name = TABLE_SCHEMA_NAMES.get(item.name)
            if schema_name is None:
                continue
            schema = schemas.get(schema_name)
            if schema is None:
                raise KlarfValidationError(
                    f"KLARF 1.2 table {item.name!r} requires a preceding "
                    f"{schema_name!r}"
                )
            if item.columns != schema.columns:
                raise KlarfValidationError(
                    f"KLARF 1.2 table {item.name!r} columns do not match "
                    f"{schema_name!r}"
                )

    def find_records(self, name: str) -> tuple[Klarf12Record, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, Klarf12Record) and item.name == name
        )

    def find_schemas(self, name: str) -> tuple[Klarf12Schema, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, Klarf12Schema) and item.name == name
        )

    def find_tables(self, name: str) -> tuple[Klarf12Table, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, Klarf12Table) and item.name == name
        )

    def find_counted_lists(self, name: str) -> tuple[Klarf12CountedList, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, Klarf12CountedList) and item.name == name
        )
