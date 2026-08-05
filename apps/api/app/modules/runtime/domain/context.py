from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.shared.domain.data_source import RuntimeDataSourceRef

if TYPE_CHECKING:
    from app.shared.context import AppContext


@dataclass(frozen=True, slots=True)
class TrainingRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str | None
    trainer_id: str
    created_by: str
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    missing_image_policy: str | None = None
    org_id: str = ""
    collection_id: str | None = None
    collection_revision_id: str | None = None

    @property
    def data_source(self) -> RuntimeDataSourceRef:
        return RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )


@dataclass(frozen=True, slots=True)
class PredictionRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str | None
    model_id: str
    org_id: str
    predictor_id: str
    created_by: str
    target: str
    model_version: str | None = None
    sample_ids: list[str] | None = None
    sample_filter: dict[str, Any] | None = None
    prompt: str | None = None
    collection_id: str | None = None
    collection_revision_id: str | None = None

    @property
    def data_source(self) -> RuntimeDataSourceRef:
        return RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )


@dataclass(frozen=True, slots=True)
class TrainAndPredictRuntimeContext:
    app_context: AppContext
    job_id: str
    dataset_id: str | None
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
    collection_id: str | None = None
    collection_revision_id: str | None = None

    @property
    def data_source(self) -> RuntimeDataSourceRef:
        return RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )


__all__ = [
    "PredictionRuntimeContext",
    "TrainAndPredictRuntimeContext",
    "TrainingRuntimeContext",
]
