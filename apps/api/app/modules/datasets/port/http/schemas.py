from __future__ import annotations

from typing import Generic, TypeAlias, TypeVar

from pydantic import BaseModel, Field

from app.modules.datasets.views.image_input.v1.schemas import (
    ImageInputV1Row as ImageInputV1Row,
)
from app.shared.api.schemas import TaskSpec
from app.shared.api.schemas import DatasetStorageMode

T = TypeVar("T")

SparseSummaryJsonScalar: TypeAlias = str | int | float | bool | None
SparseSummaryJsonValue: TypeAlias = (
    SparseSummaryJsonScalar
    | list[SparseSummaryJsonScalar]
    | dict[str, SparseSummaryJsonScalar]
    | list[dict[str, SparseSummaryJsonScalar]]
)


# ── Paginated per-view response ─────────────────────────────────────────


class ViewPaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    view_type: str
    dataset_id: str


# ── Dataset CRUD schemas ────────────────────────────────────────────────


class CreateDatasetRequest(BaseModel):
    name: str
    dataset_type: str | None = None
    task_spec: TaskSpec = Field(default_factory=TaskSpec)
    storage_mode: DatasetStorageMode = DatasetStorageMode.DB_FULL


class UpdateLabelSpaceRequest(BaseModel):
    label_space: list[str]


class UpdateDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CreateSampleRequest(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BulkCreateSampleItem(BaseModel):
    image_uris: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    label: str | None = None


class BulkCreateSampleRequest(BaseModel):
    items: list[BulkCreateSampleItem] = Field(default_factory=list)


class BulkCreateSampleResponse(BaseModel):
    dataset_id: str
    imported: int
    failed: int
    sample_ids: list[str] = Field(default_factory=list)
    ls_task_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ImportVqaJsonlResponse(BaseModel):
    dataset_id: str
    imported: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class CreateAnnotationRequest(BaseModel):
    dataset_id: str
    sample_id: str
    label: str
    annotation_value: dict | list | None = None
    created_by: str = "demo-user"


class UpdateAnnotationRequest(BaseModel):
    dataset_id: str
    label: str


class BulkAnnotationItem(BaseModel):
    sample_id: str
    label: str
    annotator: str = "platform-user"


class BulkAnnotationRequest(BaseModel):
    annotations: list[BulkAnnotationItem]


class BulkAnnotationResponse(BaseModel):
    created: int


class SyncAnnotationsResponse(BaseModel):
    synced_count: int
    errors: list[str] = Field(default_factory=list)


class LatestAnnotation(BaseModel):
    id: str
    label: str
    created_by: str
    created_at: str


class SampleWithLabels(BaseModel):
    id: str
    dataset_id: str
    image_uris: list[str]
    metadata: dict
    ls_task_id: int | None = None
    latest_annotation: LatestAnnotation | None = None
    latest_prediction: dict | None = None


class WaferPoint(BaseModel):
    id: str
    x: float
    y: float


class WaferPointsResponse(BaseModel):
    points: list[WaferPoint]
    total: int


class SampleEmbedResponse(BaseModel):
    sample_id: str
    embed_model: str
    embedding_dim: int


class UpdateSampleImageResponse(BaseModel):
    uri: str
    sample_id: str
    index: int


class PersistExportResponse(BaseModel):
    uri: str


class SimilarityNeighbor(BaseModel):
    sample_id: str
    score: float


class SimilarityResponse(BaseModel):
    sample_id: str
    neighbors: list[SimilarityNeighbor] = Field(default_factory=list)


class SparseShardSummary(BaseModel):
    shard_index: int
    row_count: int
    format: str
    byte_size: int


class SparseManifestSummary(BaseModel):
    shard_count: int
    total_rows: int
    schema_columns: list[dict[str, str]]
    created_at: str


class SparseSummaryResponse(BaseModel):
    dataset_id: str
    name: str
    dataset_type: str
    storage_mode: str
    manifest: SparseManifestSummary
    shards: list[SparseShardSummary]
    sample_rows: list[dict[str, SparseSummaryJsonValue]]
