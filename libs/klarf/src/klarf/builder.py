from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Self, TypeAlias

from klarf.errors import UnsupportedKlarfVersionError
from klarf.models import (
    KlarfColumn,
    KlarfDocument,
    KlarfField,
    KlarfList,
    KlarfRecord,
    KlarfRecordItem,
    KlarfScalar,
    KlarfValue,
)

ColumnInput: TypeAlias = KlarfColumn | tuple[str, str]


class KlarfRecordBuilder:
    """Fluent builder for a single KLARF 1.8 record."""

    def __init__(self, name: str, *identifiers: KlarfScalar) -> None:
        self._name = name
        self._identifiers = tuple(identifiers)
        self._items: list[KlarfRecordItem] = []

    def add_field(self, name: str, *values: KlarfValue) -> Self:
        self._items.append(KlarfField(name=name, values=tuple(values)))
        return self

    def add_list(
        self,
        name: str,
        *,
        columns: Iterable[ColumnInput],
        rows: Iterable[Sequence[KlarfValue]],
    ) -> Self:
        normalized_columns = tuple(
            column
            if isinstance(column, KlarfColumn)
            else KlarfColumn(data_type=column[0], name=column[1])
            for column in columns
        )
        normalized_rows = tuple(tuple(row) for row in rows)
        self._items.append(
            KlarfList(
                name=name,
                columns=normalized_columns,
                rows=normalized_rows,
            )
        )
        return self

    def add_record(self, record: KlarfRecord | KlarfRecordBuilder) -> Self:
        self._items.append(
            record.build() if isinstance(record, KlarfRecordBuilder) else record
        )
        return self

    def build(self) -> KlarfRecord:
        return KlarfRecord(
            name=self._name,
            identifiers=self._identifiers,
            items=tuple(self._items),
        )


class KlarfBuilder:
    """Builder for a KLARF file rooted at ``FileRecord``."""

    def __init__(self, version: str) -> None:
        if version != "1.8":
            raise UnsupportedKlarfVersionError(
                f"KLARF builder supports version 1.8, got {version!r}"
            )
        self._root = KlarfRecordBuilder("FileRecord", version)

    def add_field(self, name: str, *values: KlarfValue) -> Self:
        self._root.add_field(name, *values)
        return self

    def add_list(
        self,
        name: str,
        *,
        columns: Iterable[ColumnInput],
        rows: Iterable[Sequence[KlarfValue]],
    ) -> Self:
        self._root.add_list(name, columns=columns, rows=rows)
        return self

    def add_record(self, record: KlarfRecord | KlarfRecordBuilder) -> Self:
        self._root.add_record(record)
        return self

    def build(self) -> KlarfDocument:
        return KlarfDocument(root=self._root.build())
