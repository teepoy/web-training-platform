"""Private in-process value models for ML execution kernels.

These are not transport contracts. Cross-process interfaces belong in the
language-agnostic definitions maintained with ``libs/protos``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TrainingSample:
    sample_id: str
    defective_image: bytes
    reference_image: bytes
    label: str


@dataclass(frozen=True, slots=True)
class PredictionSample:
    sample_id: str
    defective_image: bytes | None
    reference_image: bytes | None


@dataclass(frozen=True, slots=True)
class Prediction:
    sample_id: str
    label: str
    confidence: float | None
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TrainingOutput:
    checkpoint: bytes
    metrics: dict[str, object]
    metadata: dict[str, object]
