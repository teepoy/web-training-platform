"""Private in-process value models for ML execution implementations.

These are not transport contracts. Cross-process interfaces belong in the
language-agnostic definitions maintained with ``libs/protos``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Prediction:
    sample_id: str
    label: str
    confidence: float | None
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TrainingOutput:
    checkpoint_path: Path
    metrics: dict[str, object]
    metadata: dict[str, object]
