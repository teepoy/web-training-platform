from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.shared.domain.data_source import RuntimeDataSourceRef


def _require_identifier(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class PredictionSubmissionOrigin(StrEnum):
    MANUAL = "manual"
    AUTOMATION = "automation"


@dataclass(frozen=True, slots=True)
class PredictionJobCommand:
    model_id: str
    org_id: str
    created_by: str
    dataset_id: str | None = None
    collection_id: str | None = None
    collection_revision_id: str | None = None
    target: str = "image_classification"
    model_version: str | None = None
    sample_ids: tuple[str, ...] | None = None
    prompt: str | None = None
    predictor_id: str | None = None
    collection_prediction_batch_id: str | None = None
    collection_member_id: str | None = None
    submission_origin: PredictionSubmissionOrigin = PredictionSubmissionOrigin.MANUAL

    def __post_init__(self) -> None:
        for field_name in (
            "model_id",
            "org_id",
            "created_by",
            "target",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        self.data_source
        if self.sample_ids is not None:
            if not self.sample_ids:
                raise ValueError("sample_ids must not be empty")
            if any(not sample_id.strip() for sample_id in self.sample_ids):
                raise ValueError("sample_ids must not contain empty IDs")
        if self.predictor_id is not None:
            _require_identifier(self.predictor_id, "predictor_id")
        for field_name in (
            "collection_prediction_batch_id",
            "collection_member_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)

    @property
    def data_source(self) -> RuntimeDataSourceRef:
        return RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )


class PredictionResourceNotFoundError(LookupError):
    pass


class PredictionSubmissionRejectedError(ValueError):
    pass


class PredictionRuntimeUnavailableError(RuntimeError):
    pass


class PredictionSubmissionError(RuntimeError):
    pass
