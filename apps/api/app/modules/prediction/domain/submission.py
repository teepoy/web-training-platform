from __future__ import annotations

from dataclasses import dataclass


def _require_identifier(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class PredictionJobCommand:
    dataset_id: str
    model_id: str
    org_id: str
    created_by: str
    target: str = "image_classification"
    model_version: str | None = None
    sample_ids: tuple[str, ...] | None = None
    prompt: str | None = None
    predictor_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_id",
            "model_id",
            "org_id",
            "created_by",
            "target",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        if self.sample_ids is not None:
            if not self.sample_ids:
                raise ValueError("sample_ids must not be empty")
            if any(not sample_id.strip() for sample_id in self.sample_ids):
                raise ValueError("sample_ids must not contain empty IDs")
        if self.predictor_id is not None:
            _require_identifier(self.predictor_id, "predictor_id")


class PredictionResourceNotFoundError(LookupError):
    pass


class PredictionSubmissionRejectedError(ValueError):
    pass


class PredictionRuntimeUnavailableError(RuntimeError):
    pass


class PredictionSubmissionError(RuntimeError):
    pass
