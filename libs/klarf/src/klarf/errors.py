from __future__ import annotations


class KlarfError(ValueError):
    """Base error for invalid KLARF input or models."""


class KlarfParseError(KlarfError):
    """Raised when KLARF text does not match the supported grammar."""

    def __init__(self, message: str, *, line: int, column: int) -> None:
        super().__init__(f"{message} at line {line}, column {column}")
        self.line = line
        self.column = column


class KlarfValidationError(KlarfError):
    """Raised when a KLARF object is structurally inconsistent."""


class UnsupportedKlarfVersionError(KlarfError):
    """Raised when input is a valid-looking but unsupported KLARF version."""
