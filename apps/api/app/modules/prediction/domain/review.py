from __future__ import annotations

from dataclasses import dataclass


def _require_identifier(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class ReviewAnnotationCommand:
    sample_id: str
    predicted_label: str
    final_label: str
    confidence: float | None = None
    prediction_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.sample_id, "sample_id")
        _require_identifier(self.predicted_label, "predicted_label")
        _require_identifier(self.final_label, "final_label")
