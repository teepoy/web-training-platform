from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.shared.context import AppContext


@dataclass(frozen=True, slots=True)
class TrainingRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str
    trainer_id: str
    created_by: str
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    missing_image_policy: str | None = None


@dataclass(frozen=True, slots=True)
class PredictionRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str
    model_id: str
    org_id: str
    predictor_id: str
    created_by: str
    target: str
    model_version: str | None = None
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    prompt: str | None = None


@dataclass(frozen=True, slots=True)
class TrainAndPredictRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str
    trainer_id: str
    predictor_id: str
    org_id: str
    created_by: str
    target: str
    model_version: str | None = None
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    prompt: str | None = None
    missing_image_policy: str | None = None


__all__ = [
    "PredictionRuntimeContext",
    "TrainAndPredictRuntimeContext",
    "TrainingRuntimeContext",
]
