from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from klarf.models import KlarfScalar, KlarfSymbol
from klarf.v12.models import (
    Klarf12CountedList,
    Klarf12Document,
    Klarf12ImageList,
    Klarf12Record,
    Klarf12Schema,
    Klarf12Table,
    Klarf12Value,
)


def _format_scalar(value: KlarfScalar) -> str:
    if isinstance(value, KlarfSymbol):
        return value.value
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def _format_value(value: Klarf12Value) -> str:
    if not isinstance(value, Klarf12ImageList):
        return _format_scalar(value)
    flattened = " ".join(
        _format_scalar(item_value) for item in value.items for item_value in item
    )
    suffix = f" {flattened}" if flattened else ""
    return f"{len(value.items)}{suffix}"


def _write_record(record: Klarf12Record) -> list[str]:
    values = "".join(f" {_format_scalar(value)}" for value in record.values)
    return [f"{record.name}{values};"]


def _write_schema(schema: Klarf12Schema) -> list[str]:
    columns = "".join(f" {column}" for column in schema.columns)
    return [f"{schema.name} {len(schema.columns)}{columns};"]


def _write_table(table: Klarf12Table) -> Iterator[str]:
    if not table.rows:
        yield f"{table.name};"
        return
    yield table.name
    for index, row in enumerate(table.rows):
        suffix = ";" if index == len(table.rows) - 1 else ""
        yield " ".join(_format_value(value) for value in row) + suffix


def _write_counted_list(counted_list: Klarf12CountedList) -> Iterator[str]:
    if not counted_list.rows:
        yield f"{counted_list.name} 0;"
        return
    yield f"{counted_list.name} {len(counted_list.rows)}"
    for index, row in enumerate(counted_list.rows):
        suffix = ";" if index == len(counted_list.rows) - 1 else ""
        yield " ".join(_format_scalar(value) for value in row) + suffix


def _iter_lines(document: Klarf12Document) -> Iterator[str]:
    major, minor = document.version
    yield f"FileVersion {major} {minor};"
    for item in document.items:
        if isinstance(item, Klarf12Record):
            yield from _write_record(item)
        elif isinstance(item, Klarf12Schema):
            yield from _write_schema(item)
        elif isinstance(item, Klarf12Table):
            yield from _write_table(item)
        else:
            yield from _write_counted_list(item)
    yield "EndOfFile;"


def dumps12(document: Klarf12Document) -> str:
    """Serialize a KLARF 1.1/1.2 document using the flat 1.2 grammar."""

    return "\n".join((*_iter_lines(document), ""))


def dump12(
    document: Klarf12Document,
    path: str | Path,
    *,
    encoding: str = "utf-8",
) -> None:
    """Serialize a KLARF 1.1/1.2 document to a file."""

    with Path(path).open("w", encoding=encoding, newline="\n") as output:
        for line in _iter_lines(document):
            output.write(line)
            output.write("\n")
