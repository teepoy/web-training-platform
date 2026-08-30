from __future__ import annotations

from dataclasses import dataclass

from app.shared.api.schemas import TrainingJob
from app.shared.domain.data_source import RuntimeDataSourceRef

from app.modules.training.domain.readiness import TrainingReadinessReport


def _require_identifier(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class TrainingJobCommand:
    trainer_id: str
    org_id: str
    created_by: str
    dataset_id: str | None = None
    collection_id: str | None = None
    collection_revision_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("trainer_id", "org_id", "created_by"):
            _require_identifier(getattr(self, field_name), field_name)
        self.data_source

    @property
    def data_source(self) -> RuntimeDataSourceRef:
        return RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )


@dataclass(frozen=True, slots=True)
class TrainAndPredictCommand(TrainingJobCommand):
    target: str = "image_classification"
    model_version: str | None = None
    sample_ids: tuple[str, ...] | None = None
    collection_member_ids: tuple[str, ...] | None = None
    sample_filter: dict[str, object] | None = None
    prompt: str | None = None
    predictor_id: str | None = None

    def __post_init__(self) -> None:
        TrainingJobCommand.__post_init__(self)
        _require_identifier(self.target, "target")
        if self.sample_ids is not None:
            if not self.sample_ids:
                raise ValueError("sample_ids must not be empty")
            if any(not sample_id.strip() for sample_id in self.sample_ids):
                raise ValueError("sample_ids must not contain empty IDs")
        if self.sample_ids is not None and self.sample_filter is not None:
            raise ValueError("sample_ids and sample_filter are mutually exclusive")
        if self.sample_filter is not None and not self.sample_filter:
            raise ValueError("sample_filter must not be empty")
        if self.collection_member_ids is not None:
            if not self.collection_member_ids or len(self.collection_member_ids) != len(
                set(self.collection_member_ids)
            ):
                raise ValueError("collection_member_ids must be non-empty and unique")
            if self.collection_id is None:
                raise ValueError("collection_member_ids require a Collection source")
        if self.predictor_id is not None:
            _require_identifier(self.predictor_id, "predictor_id")


@dataclass(frozen=True, slots=True)
class TrainAndPredictSubmission:
    train_job: TrainingJob
    workflow_run_id: str


class TrainingDatasetNotFoundError(LookupError):
    def __init__(self, dataset_id: str) -> None:
        super().__init__(f"Dataset '{dataset_id}' not found")


class TrainingReadinessError(ValueError):
    def __init__(self, report: TrainingReadinessReport) -> None:
        super().__init__("dataset is not ready for training")
        self.report = report


class TrainingRuntimeUnavailableError(RuntimeError):
    pass


class TrainingSubmissionError(RuntimeError):
    pass
