"""Worker-only demo ML runtime domain type re-exports."""

from __future__ import annotations

from app.shared.domain.runtime import (
    BatchPredictResult,
    DatasetRef,
    ModelRef,
    PredictContext,
    PredictResult,
    TrainContext,
    TrainResult,
)


__all__ = [
    "BatchPredictResult",
    "DatasetRef",
    "ModelRef",
    "PredictContext",
    "PredictResult",
    "TrainContext",
    "TrainResult",
]
