from __future__ import annotations

from pathlib import Path

from klarf._tokens import (
    NUMBER_PATTERN as _NUMBER_PATTERN,
    Token as _Token,
    as_scalar as _as_scalar,
    tokenize as _tokenize,
)
from klarf.errors import KlarfParseError, UnsupportedKlarfVersionError
from klarf.models import (
    KlarfArray,
    KlarfColumn,
    KlarfDocument,
    KlarfField,
    KlarfList,
    KlarfRecord,
    KlarfRecordItem,
    KlarfScalar,
    KlarfValue,
)


class _Parser:
    def __init__(self, text: str) -> None:
        self._tokens = _tokenize(text)
        self._index = 0

    def _peek(self, distance: int = 0) -> _Token:
        return self._tokens[min(self._index + distance, len(self._tokens) - 1)]

    def _pop(self) -> _Token:
        token = self._peek()
        self._index += 1
        return token

    def _error(self, message: str, token: _Token | None = None) -> KlarfParseError:
        location = token or self._peek()
        return KlarfParseError(
            message,
            line=location.line,
            column=location.column,
        )

    def _expect_kind(self, kind: str) -> _Token:
        token = self._pop()
        if token.kind != kind:
            raise self._error(f"expected {kind!r}, got {token.value!r}", token)
        return token

    def _expect_atom(self, value: str | None = None) -> _Token:
        token = self._expect_kind("ATOM")
        if value is not None and token.value != value:
            raise self._error(f"expected {value!r}, got {token.value!r}", token)
        return token

    def _expect_count(self, role: str) -> int:
        token = self._pop()
        scalar = _as_scalar(token)
        if isinstance(scalar, bool) or not isinstance(scalar, int) or scalar < 0:
            raise self._error(f"{role} must be a non-negative integer", token)
        return scalar

    def _parse_value(self) -> KlarfValue:
        if (
            self._peek().kind == "ATOM"
            and self._peek(1).kind == "ATOM"
            and _NUMBER_PATTERN.fullmatch(self._peek(1).value)
            and self._peek(2).kind == "{"
        ):
            return self._parse_array()
        return _as_scalar(self._pop())

    def _parse_array(self) -> KlarfArray:
        name = self._expect_atom().value
        declared_count = self._expect_count(f"array {name!r} item count")
        self._expect_kind("{")
        items: list[tuple[KlarfScalar, ...]] = []
        current: list[KlarfScalar] = []
        while self._peek().kind != "}":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated array {name!r}")
            if self._peek().kind == ",":
                self._pop()
                if not current:
                    raise self._error(f"array {name!r} contains an empty item")
                items.append(tuple(current))
                current = []
                continue
            current.append(_as_scalar(self._pop()))
        self._pop()
        if current:
            items.append(tuple(current))
        if len(items) != declared_count:
            raise self._error(
                f"array {name!r} declares {declared_count} items but contains "
                f"{len(items)}"
            )
        return KlarfArray(name=name, items=tuple(items))

    def _parse_field(self) -> KlarfField:
        name_token = self._expect_atom()
        declared_count = self._expect_count(f"field {name_token.value!r} value count")
        self._expect_kind("{")
        values: list[KlarfValue] = []
        while self._peek().kind != "}":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated field {name_token.value!r}")
            if self._peek().kind == ",":
                self._pop()
                continue
            values.append(self._parse_value())
        closing = self._pop()
        if len(values) != declared_count:
            raise self._error(
                f"field {name_token.value!r} declares {declared_count} values but "
                f"contains {len(values)}",
                closing,
            )
        return KlarfField(name=name_token.value, values=tuple(values))

    def _parse_columns(self, list_name: str) -> tuple[KlarfColumn, ...]:
        declared_count = self._expect_count(f"list {list_name!r} column count")
        self._expect_kind("{")
        columns: list[KlarfColumn] = []
        while self._peek().kind != "}":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated columns for list {list_name!r}")
            if self._peek().kind == ",":
                self._pop()
                continue
            data_type = self._expect_atom().value
            name = self._expect_atom().value
            columns.append(KlarfColumn(data_type=data_type, name=name))
        closing = self._pop()
        if len(columns) != declared_count:
            raise self._error(
                f"list {list_name!r} declares {declared_count} columns but contains "
                f"{len(columns)}",
                closing,
            )
        return tuple(columns)

    def _parse_rows(
        self,
        list_name: str,
        *,
        column_count: int,
    ) -> tuple[tuple[KlarfValue, ...], ...]:
        declared_count = self._expect_count(f"list {list_name!r} row count")
        self._expect_kind("{")
        rows: list[tuple[KlarfValue, ...]] = []
        while self._peek().kind != "}":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated data for list {list_name!r}")
            row: list[KlarfValue] = []
            row_start = self._peek()
            while self._peek().kind != ";":
                if self._peek().kind in {"EOF", "}"}:
                    raise self._error(
                        f"list {list_name!r} row is missing its semicolon",
                        row_start,
                    )
                if self._peek().kind == ",":
                    self._pop()
                    continue
                row.append(self._parse_value())
            self._pop()
            if len(row) != column_count:
                raise self._error(
                    f"list {list_name!r} row has {len(row)} values; expected "
                    f"{column_count}",
                    row_start,
                )
            rows.append(tuple(row))
        closing = self._pop()
        if len(rows) != declared_count:
            raise self._error(
                f"list {list_name!r} declares {declared_count} rows but contains "
                f"{len(rows)}",
                closing,
            )
        return tuple(rows)

    def _parse_list(self) -> KlarfList:
        name = self._expect_atom().value
        self._expect_kind("{")
        self._expect_atom("Columns")
        columns = self._parse_columns(name)
        self._expect_atom("Data")
        rows = self._parse_rows(name, column_count=len(columns))
        self._expect_kind("}")
        return KlarfList(name=name, columns=columns, rows=rows)

    def _parse_record(self) -> KlarfRecord:
        name = self._expect_atom().value
        identifiers: list[KlarfScalar] = []
        while self._peek().kind != "{":
            if self._peek().kind in {"EOF", "}"}:
                raise self._error(f"record {name!r} is missing its body")
            identifiers.append(_as_scalar(self._pop()))
        self._pop()
        items: list[KlarfRecordItem] = []
        while self._peek().kind != "}":
            if self._peek().kind == "EOF":
                raise self._error(f"unterminated record {name!r}")
            item_type = self._expect_atom().value
            if item_type == "Field":
                items.append(self._parse_field())
            elif item_type == "List":
                items.append(self._parse_list())
            elif item_type == "Record":
                items.append(self._parse_record())
            else:
                raise self._error(
                    f"unexpected record item {item_type!r}; expected Field, List, or Record"
                )
        self._pop()
        return KlarfRecord(
            name=name,
            identifiers=tuple(identifiers),
            items=tuple(items),
        )

    def parse(self) -> KlarfDocument:
        first = self._peek()
        if first.kind == "ATOM" and first.value == "FileVersion":
            raise UnsupportedKlarfVersionError(
                "legacy KLARF 1.2 syntax is not supported; expected KLARF 1.8"
            )
        self._expect_atom("Record")
        root = self._parse_record()
        self._expect_atom("EndOfFile")
        self._expect_kind(";")
        self._expect_kind("EOF")
        document = KlarfDocument(root=root)
        if document.version != "1.8":
            raise UnsupportedKlarfVersionError(
                f"KLARF loader supports version 1.8, got {document.version!r}"
            )
        return document


def loads(text: str) -> KlarfDocument:
    """Parse KLARF 1.8 text into an immutable document."""

    return _Parser(text).parse()


def load(path: str | Path, *, encoding: str = "utf-8") -> KlarfDocument:
    """Load and parse a KLARF 1.8 file."""

    return loads(Path(path).read_text(encoding=encoding))
