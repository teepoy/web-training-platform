from __future__ import annotations

from pathlib import Path

from klarf._tokens import Token, as_scalar, tokenize
from klarf.errors import KlarfParseError, UnsupportedKlarfVersionError
from klarf.models import KlarfScalar
from klarf.v12.models import (
    COUNTED_LIST_WIDTHS,
    SUPPORTED_VERSIONS,
    TABLE_SCHEMA_NAMES,
    Klarf12CountedList,
    Klarf12Document,
    Klarf12ImageList,
    Klarf12Item,
    Klarf12Record,
    Klarf12Schema,
    Klarf12Table,
    Klarf12Value,
    Klarf12Version,
)


class _Klarf12Parser:
    def __init__(self, text: str) -> None:
        self._tokens = tokenize(text)
        self._index = 0
        self._schemas: dict[str, Klarf12Schema] = {}

    def _peek(self) -> Token:
        return self._tokens[min(self._index, len(self._tokens) - 1)]

    def _pop(self) -> Token:
        token = self._peek()
        self._index += 1
        return token

    def _error(self, message: str, token: Token | None = None) -> KlarfParseError:
        location = token or self._peek()
        return KlarfParseError(
            message,
            line=location.line,
            column=location.column,
        )

    def _expect_kind(self, kind: str) -> Token:
        token = self._pop()
        if token.kind != kind:
            raise self._error(f"expected {kind!r}, got {token.value!r}", token)
        return token

    def _expect_atom(self, value: str | None = None) -> Token:
        token = self._expect_kind("ATOM")
        if value is not None and token.value != value:
            raise self._error(f"expected {value!r}, got {token.value!r}", token)
        return token

    def _expect_count(self, role: str) -> int:
        token = self._pop()
        value = as_scalar(token)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise self._error(f"{role} must be a non-negative integer", token)
        return value

    def _expect_semicolon(self) -> None:
        self._expect_kind(";")

    def _parse_version(self) -> Klarf12Version:
        first = self._peek()
        if first.kind == "ATOM" and first.value == "Record":
            raise UnsupportedKlarfVersionError(
                "KLARF 1.2 parser cannot parse hierarchical KLARF 1.8 syntax"
            )
        self._expect_atom("FileVersion")
        major = self._expect_count("FileVersion major version")
        minor = self._expect_count("FileVersion minor version")
        self._expect_semicolon()
        version = (major, minor)
        if version not in SUPPORTED_VERSIONS:
            raise UnsupportedKlarfVersionError(
                f"KLARF 1.2 parser does not support FileVersion {major}.{minor}"
            )
        return version

    def _parse_record(self, name: str) -> Klarf12Record:
        values: list[KlarfScalar] = []
        while self._peek().kind != ";":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated KLARF 1.2 record {name!r}")
            values.append(as_scalar(self._pop()))
        self._expect_semicolon()
        return Klarf12Record(name=name, values=tuple(values))

    def _parse_schema(self, name: str) -> Klarf12Schema:
        declared_count = self._expect_count(f"schema {name!r} column count")
        columns: list[str] = []
        for _ in range(declared_count):
            columns.append(self._expect_atom().value)
        if self._peek().kind != ";":
            raise self._error(
                f"schema {name!r} declares {declared_count} columns but contains more"
            )
        self._expect_semicolon()
        schema = Klarf12Schema(name=name, columns=tuple(columns))
        self._schemas[name] = schema
        return schema

    def _parse_image_list(
        self,
        *,
        image_count: int | None,
    ) -> Klarf12ImageList:
        token = self._peek()
        declared_count = self._expect_count("IMAGELIST item count")
        if image_count is not None and image_count != declared_count:
            raise self._error(
                f"IMAGECOUNT is {image_count} but IMAGELIST declares {declared_count}",
                token,
            )
        items: list[tuple[KlarfScalar, KlarfScalar]] = []
        for _ in range(declared_count):
            first = as_scalar(self._pop())
            second = as_scalar(self._pop())
            items.append((first, second))
        return Klarf12ImageList(items=tuple(items))

    def _parse_table_row(
        self,
        *,
        table_name: str,
        columns: tuple[str, ...],
    ) -> tuple[Klarf12Value, ...]:
        row_start = self._peek()
        values: list[Klarf12Value] = []
        image_count: int | None = None
        for column in columns:
            if self._peek().kind in {";", "EOF"}:
                raise self._error(
                    f"KLARF 1.2 table {table_name!r} row ended before column "
                    f"{column!r}",
                    row_start,
                )
            if column.upper() == "IMAGELIST":
                values.append(self._parse_image_list(image_count=image_count))
                continue
            value = as_scalar(self._pop())
            values.append(value)
            if column.upper() == "IMAGECOUNT":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise self._error(
                        "IMAGECOUNT must be a non-negative integer",
                        row_start,
                    )
                image_count = value
        return tuple(values)

    def _parse_table(self, name: str, schema_name: str) -> Klarf12Table:
        schema = self._schemas.get(schema_name)
        if schema is None:
            raise self._error(
                f"KLARF 1.2 table {name!r} requires a preceding {schema_name!r}"
            )
        rows: list[tuple[Klarf12Value, ...]] = []
        while self._peek().kind != ";":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated KLARF 1.2 table {name!r}")
            rows.append(
                self._parse_table_row(
                    table_name=name,
                    columns=schema.columns,
                )
            )
        self._expect_semicolon()
        return Klarf12Table(
            name=name,
            columns=schema.columns,
            rows=tuple(rows),
        )

    def _parse_counted_list(self, name: str, width: int) -> Klarf12CountedList:
        declared_count = self._expect_count(f"counted list {name!r} row count")
        rows: list[tuple[KlarfScalar, ...]] = []
        for _ in range(declared_count):
            row_start = self._peek()
            row: list[KlarfScalar] = []
            for _ in range(width):
                if self._peek().kind in {";", "EOF"}:
                    raise self._error(
                        f"KLARF 1.2 counted list {name!r} row has fewer than "
                        f"{width} values",
                        row_start,
                    )
                row.append(as_scalar(self._pop()))
            rows.append(tuple(row))
        if self._peek().kind != ";":
            raise self._error(
                f"KLARF 1.2 counted list {name!r} declares {declared_count} "
                "rows but contains more data"
            )
        self._expect_semicolon()
        return Klarf12CountedList(name=name, rows=tuple(rows))

    def parse(self) -> Klarf12Document:
        version = self._parse_version()
        items: list[Klarf12Item] = []
        while True:
            name_token = self._expect_atom()
            name = name_token.value
            if name == "EndOfFile":
                self._expect_semicolon()
                self._expect_kind("EOF")
                break
            if name in TABLE_SCHEMA_NAMES.values():
                items.append(self._parse_schema(name))
                continue
            schema_name = TABLE_SCHEMA_NAMES.get(name)
            if schema_name is not None:
                items.append(self._parse_table(name, schema_name))
                continue
            counted_width = COUNTED_LIST_WIDTHS.get(name)
            if counted_width is not None:
                items.append(self._parse_counted_list(name, counted_width))
                continue
            items.append(self._parse_record(name))
        return Klarf12Document(version=version, items=tuple(items))


def loads12(text: str) -> Klarf12Document:
    """Parse flat KLARF 1.1/1.2 text using the independent 1.2 grammar."""

    return _Klarf12Parser(text).parse()


def load12(path: str | Path, *, encoding: str = "utf-8") -> Klarf12Document:
    """Load a flat KLARF 1.1/1.2 file."""

    return loads12(Path(path).read_text(encoding=encoding))
