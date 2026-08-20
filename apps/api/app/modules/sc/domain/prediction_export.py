from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScPredictionExportFormat(StrEnum):
    KLARF = "klarf"
    PARQUET = "parquet"
    ZIP = "zip"


class ScKlarfVersion(StrEnum):
    V1_2 = "1.2"
    V1_8 = "1.8"


@dataclass(frozen=True, slots=True)
class ScPredictionExportResult:
    uri: str
    format: ScPredictionExportFormat
    row_count: int
    sampled: bool
    filename: str
    klarf_version: ScKlarfVersion | None
