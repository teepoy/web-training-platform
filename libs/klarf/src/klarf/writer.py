from __future__ import annotations

import json
from pathlib import Path

from klarf.errors import UnsupportedKlarfVersionError
from klarf.models import (
    KlarfArray,
    KlarfDocument,
    KlarfField,
    KlarfList,
    KlarfRecord,
    KlarfScalar,
    KlarfSymbol,
    KlarfValue,
)


def _format_scalar(value: KlarfScalar) -> str:
    if isinstance(value, KlarfSymbol):
        return value.value
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def _format_value(value: KlarfValue) -> str:
    if not isinstance(value, KlarfArray):
        return _format_scalar(value)
    items = ", ".join(
        " ".join(_format_scalar(item_value) for item_value in item)
        for item in value.items
    )
    return f"{value.name} {len(value.items)} {{ {items} }}"


def _write_field(field: KlarfField, indent: int) -> list[str]:
    padding = "  " * indent
    values = ", ".join(_format_value(value) for value in field.values)
    return [f"{padding}Field {field.name} {len(field.values)} {{{values}}}"]


def _write_list(klarf_list: KlarfList, indent: int) -> list[str]:
    padding = "  " * indent
    body_padding = "  " * (indent + 1)
    row_padding = "  " * (indent + 2)
    columns = ", ".join(
        f"{column.data_type} {column.name}" for column in klarf_list.columns
    )
    lines = [
        f"{padding}List {klarf_list.name}",
        f"{padding}{{",
        f"{body_padding}Columns {len(klarf_list.columns)} {{ {columns} }}",
        f"{body_padding}Data {len(klarf_list.rows)}",
        f"{body_padding}{{",
    ]
    lines.extend(
        f"{row_padding}{' '.join(_format_value(value) for value in row)};"
        for row in klarf_list.rows
    )
    lines.extend((f"{body_padding}}}", f"{padding}}}"))
    return lines


def _write_record(record: KlarfRecord, indent: int) -> list[str]:
    padding = "  " * indent
    identifiers = "".join(
        f" {_format_scalar(identifier)}" for identifier in record.identifiers
    )
    lines = [f"{padding}Record {record.name}{identifiers}", f"{padding}{{"]
    for item in record.items:
        if isinstance(item, KlarfField):
            lines.extend(_write_field(item, indent + 1))
        elif isinstance(item, KlarfList):
            lines.extend(_write_list(item, indent + 1))
        else:
            lines.extend(_write_record(item, indent + 1))
    lines.append(f"{padding}}}")
    return lines


def dumps(document: KlarfDocument) -> str:
    """Serialize a KLARF 1.8 document using deterministic formatting."""

    if document.version != "1.8":
        raise UnsupportedKlarfVersionError(
            f"KLARF writer supports version 1.8, got {document.version!r}"
        )
    return "\n".join((*_write_record(document.root, 0), "EndOfFile;", ""))


def dump(
    document: KlarfDocument,
    path: str | Path,
    *,
    encoding: str = "utf-8",
) -> None:
    """Serialize a KLARF 1.8 document to a file."""

    Path(path).write_text(dumps(document), encoding=encoding)
