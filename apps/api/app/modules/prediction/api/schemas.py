from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RunPredictionRequest(BaseModel):
    """Request to run predictions on a dataset using a model."""

    model_id: str = Field(description="ID of the model artifact to use")
    dataset_id: str = Field(description="ID of the dataset to run predictions on")
    sample_ids: list[str] | None = Field(
        default=None,
        description="Optional list of sample IDs. If None, runs on all samples in dataset",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )
    target: str = Field(
        default="image_classification", description="Prediction target key in preset"
    )
    prompt: str | None = Field(
        default=None, description="Optional runtime prompt/question override"
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
    dataset_id: str
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


class PredictSingleRequest(BaseModel):
    """Request to predict a single sample."""

    model_id: str = Field(description="ID of the model artifact to use")
    sample_id: str = Field(description="ID of the sample to predict")
    model_version: str | None = Field(
        default=None,
        description="Optional version tag for Label Studio filtering",
    )
    target: str = Field(
        default="image_classification", description="Prediction target key in preset"
    )
    prompt: str | None = Field(
        default=None, description="Optional runtime prompt/question override"
    )


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
