from __future__ import annotations

import re
from dataclasses import dataclass

from klarf.errors import KlarfParseError
from klarf.models import KlarfScalar, KlarfSymbol

NUMBER_PATTERN = re.compile(r"^[+-]?(?:(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)$")
_PUNCTUATION = {"{", "}", ",", ";"}


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


def tokenize(text: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    offset = 0
    line = 1
    column = 1

    def advance(value: str) -> None:
        nonlocal line, column
        newline_count = value.count("\n")
        if newline_count:
            line += newline_count
            column = len(value.rsplit("\n", maxsplit=1)[-1]) + 1
        else:
            column += len(value)

    while offset < len(text):
        character = text[offset]
        if character == "\ufeff" and offset == 0:
            offset += 1
            column += 1
            continue
        if character.isspace():
            advance(character)
            offset += 1
            continue
        if text.startswith("//", offset):
            end = text.find("\n", offset)
            if end == -1:
                break
            comment = text[offset:end]
            advance(comment)
            offset = end
            continue
        if text.startswith("/*", offset):
            end = text.find("*/", offset + 2)
            if end == -1:
                raise KlarfParseError(
                    "unterminated block comment",
                    line=line,
                    column=column,
                )
            comment = text[offset : end + 2]
            advance(comment)
            offset = end + 2
            continue
        if character in _PUNCTUATION:
            tokens.append(Token(character, character, line, column))
            offset += 1
            column += 1
            continue
        if character == '"':
            token_line = line
            token_column = column
            offset += 1
            column += 1
            quoted_value: list[str] = []
            while offset < len(text):
                character = text[offset]
                if character == '"':
                    offset += 1
                    column += 1
                    tokens.append(
                        Token(
                            "STRING",
                            "".join(quoted_value),
                            token_line,
                            token_column,
                        )
                    )
                    break
                if character == "\n" or character == "\r":
                    raise KlarfParseError(
                        "newline in quoted string",
                        line=line,
                        column=column,
                    )
                if character == "\\":
                    if offset + 1 >= len(text):
                        raise KlarfParseError(
                            "unterminated string escape",
                            line=line,
                            column=column,
                        )
                    escaped = text[offset + 1]
                    replacements = {
                        '"': '"',
                        "\\": "\\",
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                    }
                    if escaped not in replacements:
                        raise KlarfParseError(
                            f"unsupported string escape \\{escaped}",
                            line=line,
                            column=column,
                        )
                    quoted_value.append(replacements[escaped])
                    offset += 2
                    column += 2
                    continue
                quoted_value.append(character)
                offset += 1
                column += 1
            else:
                raise KlarfParseError(
                    "unterminated quoted string",
                    line=token_line,
                    column=token_column,
                )
            continue

        token_line = line
        token_column = column
        end = offset
        while (
            end < len(text)
            and not text[end].isspace()
            and text[end] not in _PUNCTUATION
            and text[end] != '"'
        ):
            end += 1
        if end == offset:
            raise KlarfParseError(
                f"unexpected character {character!r}",
                line=line,
                column=column,
            )
        atom_value = text[offset:end]
        tokens.append(Token("ATOM", atom_value, token_line, token_column))
        advance(atom_value)
        offset = end

    tokens.append(Token("EOF", "", line, column))
    return tuple(tokens)


def as_scalar(token: Token) -> KlarfScalar:
    if token.kind == "STRING":
        return token.value
    if token.kind != "ATOM":
        raise KlarfParseError(
            "expected a KLARF value",
            line=token.line,
            column=token.column,
        )
    if NUMBER_PATTERN.fullmatch(token.value):
        if "." in token.value or "e" in token.value.lower():
            return float(token.value)
        return int(token.value)
    return KlarfSymbol(token.value)
