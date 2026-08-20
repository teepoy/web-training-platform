from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TypeAlias, Union

from klarf.errors import KlarfValidationError

_NAME_PATTERN = re.compile(r"^[^\s{},;\"]+$")


def _validate_name(value: str, *, role: str) -> None:
    if not value or _NAME_PATTERN.fullmatch(value) is None:
        raise KlarfValidationError(f"{role} must be a non-empty KLARF atom: {value!r}")


@dataclass(frozen=True, slots=True)
class KlarfSymbol:
    """An unquoted KLARF atom, such as ``N`` or ``WAFER``."""

    value: str

    def __post_init__(self) -> None:
        _validate_name(self.value, role="symbol")


KlarfScalar: TypeAlias = str | int | float | KlarfSymbol


def _validate_scalar(value: KlarfScalar) -> None:
    if isinstance(value, bool):
        raise KlarfValidationError("boolean values are not part of KLARF syntax")
    if isinstance(value, float) and not math.isfinite(value):
        raise KlarfValidationError("KLARF numeric values must be finite")
    if not isinstance(value, str | int | float | KlarfSymbol):
        raise KlarfValidationError(f"unsupported KLARF value: {value!r}")


@dataclass(frozen=True, slots=True)
class KlarfArray:
    """A compound list cell, for example ``Images 2 {...}``."""

    name: str
    items: tuple[tuple[KlarfScalar, ...], ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="array name")
        for item in self.items:
            for value in item:
                _validate_scalar(value)


KlarfValue: TypeAlias = KlarfScalar | KlarfArray


@dataclass(frozen=True, slots=True)
class KlarfColumn:
    data_type: str
    name: str

    def __post_init__(self) -> None:
        _validate_name(self.data_type, role="column data type")
        _validate_name(self.name, role="column name")


@dataclass(frozen=True, slots=True)
class KlarfField:
    name: str
    values: tuple[KlarfValue, ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="field name")
        for value in self.values:
            if isinstance(value, KlarfArray):
                continue
            _validate_scalar(value)


@dataclass(frozen=True, slots=True)
class KlarfList:
    name: str
    columns: tuple[KlarfColumn, ...]
    rows: tuple[tuple[KlarfValue, ...], ...]

    def __post_init__(self) -> None:
        _validate_name(self.name, role="list name")
        column_names = [column.name for column in self.columns]
        if len(column_names) != len(set(column_names)):
            raise KlarfValidationError(
                f"list {self.name!r} contains duplicate column names"
            )
        for row_number, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise KlarfValidationError(
                    f"list {self.name!r} row {row_number} has {len(row)} values; "
                    f"expected {len(self.columns)}"
                )
            for value in row:
                if isinstance(value, KlarfArray):
                    continue
                _validate_scalar(value)

    def as_dicts(self) -> tuple[dict[str, KlarfValue], ...]:
        """Return rows keyed by their dynamic column names."""

        names = tuple(column.name for column in self.columns)
        return tuple(dict(zip(names, row, strict=True)) for row in self.rows)


KlarfRecordItem: TypeAlias = Union[KlarfField, KlarfList, "KlarfRecord"]


@dataclass(frozen=True, slots=True)
class KlarfRecord:
    name: str
    identifiers: tuple[KlarfScalar, ...] = ()
    items: tuple[KlarfRecordItem, ...] = ()

    def __post_init__(self) -> None:
        _validate_name(self.name, role="record name")
        for identifier in self.identifiers:
            _validate_scalar(identifier)

    def find_fields(self, name: str) -> tuple[KlarfField, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, KlarfField) and item.name == name
        )

    def find_lists(self, name: str) -> tuple[KlarfList, ...]:
        return tuple(
            item
            for item in self.items
            if isinstance(item, KlarfList) and item.name == name
        )

    def find_records(
        self,
        name: str,
        *,
        recursive: bool = True,
    ) -> tuple[KlarfRecord, ...]:
        matches: list[KlarfRecord] = []
        for item in self.items:
            if not isinstance(item, KlarfRecord):
                continue
            if item.name == name:
                matches.append(item)
            if recursive:
                matches.extend(item.find_records(name, recursive=True))
        return tuple(matches)


@dataclass(frozen=True, slots=True)
class KlarfDocument:
    root: KlarfRecord

    def __post_init__(self) -> None:
        if self.root.name != "FileRecord":
            raise KlarfValidationError("KLARF 1.8 root record must be FileRecord")
        if not self.root.identifiers or not isinstance(self.root.identifiers[0], str):
            raise KlarfValidationError(
                "FileRecord must start with a quoted KLARF version identifier"
            )

    @property
    def version(self) -> str:
        version = self.root.identifiers[0]
        assert isinstance(version, str)
        return version

    def find_records(self, name: str) -> tuple[KlarfRecord, ...]:
        if self.root.name == name:
            return (self.root, *self.root.find_records(name))
        return self.root.find_records(name)
