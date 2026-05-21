from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.models import TaskSpec
from app.domain.types import DatasetStorageMode, DatasetType


class CreateDatasetRequest(BaseModel):
    name: str
    dataset_type: DatasetType | None = None
    task_spec: TaskSpec = Field(default_factory=TaskSpec)
    storage_mode: DatasetStorageMode = DatasetStorageMode.DB_FULL


class UpdateLabelSpaceRequest(BaseModel):
    label_space: list[str]


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
    sample_id: str
    label: str
    annotation_value: dict | list | None = None
    created_by: str = "demo-user"


class UpdateAnnotationRequest(BaseModel):
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


class EmbedConfigResponse(BaseModel):
    model: str
    dimension: int = 512


class UpdateEmbedConfigRequest(BaseModel):
    model: str
    dimension: int = 512


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
    sample_rows: list[dict[str, object]]
