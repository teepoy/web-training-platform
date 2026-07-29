from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PredictionResult(BaseModel):
    """Application-facing result for one prediction."""

    id: str | None = None
    sample_id: str
    predicted_label: str
    confidence: float | None
    all_scores: dict[str, float] | None = None
    model_id: str | None = None
    target: str | None = None
    model_version: str | None = None
    job_id: str | None = None
    created_at: datetime | None = None
    error: str | None = None


class BatchPredictionResult(BaseModel):
    """Application-facing result for a completed prediction batch."""

    model_id: str
    dataset_id: str
    total_samples: int
    successful: int
    failed: int
    predictions: list[PredictionResult]
    started_at: datetime
    completed_at: datetime
    model_version: str | None = None
