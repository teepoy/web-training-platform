from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.prediction.domain.review import ReviewAnnotationCommand
from app.modules.prediction.domain.submission import PredictionJobCommand


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunPredictionRequest(StrictRequest):
    """Request to run predictions on a dataset using a model."""

    model_id: str = Field(min_length=1, description="ID of the model artifact to use")
    dataset_id: str | None = Field(
        default=None,
        min_length=1,
        description="ID of the dataset to run predictions on",
    )
    collection_id: str | None = Field(default=None, min_length=1)
    collection_revision_id: str | None = Field(default=None, min_length=1)
    sample_ids: list[str] | None = Field(
        default=None,
        min_length=1,
        description="Optional list of sample IDs. If None, runs on all samples in dataset",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )
    target: str = Field(
        default="image_classification",
        min_length=1,
        description="Prediction target key in trainer",
    )
    prompt: str | None = Field(
        default=None, description="Optional runtime prompt/question override"
    )
    predictor_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Explicit predictor paired with the model's trainer; required when "
            "the trainer declares multiple predictors"
        ),
    )

    @model_validator(mode="after")
    def validate_data_source(self) -> RunPredictionRequest:
        from app.shared.domain.data_source import RuntimeDataSourceRef

        RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )
        return self

    def to_command(self, *, org_id: str, created_by: str) -> PredictionJobCommand:
        return PredictionJobCommand(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
            model_id=self.model_id,
            org_id=org_id,
            created_by=created_by,
            target=self.target,
            model_version=self.model_version,
            sample_ids=tuple(self.sample_ids) if self.sample_ids is not None else None,
            prompt=self.prompt,
            predictor_id=self.predictor_id,
        )


class PredictionResultResponse(BaseModel):
    """Result of a single sample prediction."""

    id: str | None = None
    sample_id: str
    predicted_label: str
    confidence: float | None = None
    model_id: str | None = None
    target: str | None = None
    model_version: str | None = None
    job_id: str | None = None
    created_at: datetime | None = None
    error: str | None = None


class PredictionJobResponse(BaseModel):
    id: str
    dataset_id: str | None
    dataset_revision_id: str | None = Field(
        default=None,
        description=(
            "Dataset Revision observed at submission time; audit-only and does "
            "not select the runtime input"
        ),
    )
    collection_id: str | None = None
    collection_revision_id: str | None = None
    model_id: str
    status: str
    created_by: str
    target: str
    model_version: str | None = None
    created_at: datetime
    updated_at: datetime
    external_job_id: str | None = None
    sample_ids: list[str] | None = None
    summary: dict = Field(default_factory=dict)


class PredictionEventResponse(BaseModel):
    job_id: str
    ts: datetime
    level: str
    message: str
    payload: dict = Field(default_factory=dict)


class BatchPredictionResponse(BaseModel):
    """Response for batch prediction run."""

    model_id: str
    dataset_id: str
    total_samples: int
    successful: int
    failed: int
    predictions: list[PredictionResultResponse]
    started_at: datetime
    completed_at: datetime
    model_version: str | None = None


class PredictSingleRequest(StrictRequest):
    """Request to predict a single sample."""

    dataset_id: str = Field(
        min_length=1,
        description="ID of the dataset containing the sample",
    )
    model_id: str = Field(
        min_length=1,
        description="ID of the model artifact to use",
    )
    sample_id: str = Field(min_length=1, description="ID of the sample to predict")
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )
    target: str = Field(
        default="image_classification",
        min_length=1,
        description="Prediction target key in trainer",
    )
    prompt: str | None = Field(
        default=None, description="Optional runtime prompt/question override"
    )
    predictor_id: str | None = Field(default=None, min_length=1)


class CreateReviewActionRequest(BaseModel):
    """Request to start a prediction review session."""

    dataset_id: str = Field(description="ID of the dataset")
    model_id: str = Field(description="ID of the model used for predictions")
    collection_id: str | None = Field(
        default=None, description="Optional prediction collection used for manual sync"
    )
    sync_tag: str | None = Field(
        default=None,
        description="Optional LS sync tag for the temporary manual annotation batch",
    )
    model_version: str | None = Field(
        default=None,
        description="Version tag used when running predictions",
    )


class ReviewActionResponse(BaseModel):
    """Response for a prediction review action."""

    id: str
    dataset_id: str
    model_id: str
    model_version: str | None = None
    collection_id: str | None = None
    sync_tag: str | None = None
    created_by: str
    created_at: datetime


class SaveReviewAnnotationItem(BaseModel):
    """Single reviewed prediction to save as annotation."""

    sample_id: str
    predicted_label: str
    final_label: str
    confidence: float | None = None
    prediction_id: str | None = None

    def to_command(self) -> ReviewAnnotationCommand:
        return ReviewAnnotationCommand(
            sample_id=self.sample_id,
            predicted_label=self.predicted_label,
            final_label=self.final_label,
            confidence=self.confidence,
            prediction_id=self.prediction_id,
        )


class SaveReviewAnnotationsRequest(BaseModel):
    """Request to save reviewed predictions as annotations for a review action."""

    items: list[SaveReviewAnnotationItem]


class AnnotationVersionResponse(BaseModel):
    """Response for a single annotation version entry."""

    id: str
    review_action_id: str
    annotation_id: str
    prediction_id: str | None = None
    predicted_label: str
    final_label: str
    confidence: float | None = None
    created_at: datetime


class PredictionCollectionRequest(BaseModel):
    name: str
    dataset_id: str
    model_id: str
    prediction_ids: list[str] = Field(default_factory=list)
    model_version: str | None = None
    target: str = "image_classification"
    source_job_id: str | None = None


class PredictionCollectionResponse(BaseModel):
    id: str
    name: str
    dataset_id: str
    model_id: str
    model_version: str | None = None
    target: str
    source_job_id: str | None = None
    sync_tag: str | None = None
    created_by: str
    created_at: datetime
    prediction_ids: list[str] = Field(default_factory=list)


class SyncPredictionCollectionRequest(BaseModel):
    sync_tag: str | None = None


class SyncPredictionCollectionResponse(BaseModel):
    collection_id: str
    sync_tag: str
    synced_count: int
    failed_count: int
    errors: list[str] = Field(default_factory=list)


class SaveReviewAnnotationsResponse(BaseModel):
    """Response after saving reviewed annotations."""

    review_action_id: str
    created_count: int
    annotation_versions: list[AnnotationVersionResponse]


class ExportFormatResponse(BaseModel):
    """Available export format descriptor."""

    format_id: str


class VersionExportRequest(BaseModel):
    """Request to export an annotation version."""

    format_id: str = Field(
        default="annotation-version-full-context-v1",
        description="Export format identifier",
    )


class VersionExportPersistResponse(BaseModel):
    uri: str
    format_id: str
