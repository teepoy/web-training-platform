from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScInspectionSummaryItem(BaseModel):
    inspection_time: str
    wafer_key: int
    lot_id: str
    wafer_id: str
    center_x: int
    center_y: int
    origin_x: int
    origin_y: int
    die_size_x: int
    die_size_y: int
    layer_id: str
    eqp_id: str
    recipe_id: str
    defects: int
    images: int
    device: str


class ScInspectionListResponse(BaseModel):
    items: list[ScInspectionSummaryItem]
    total: int


class ScReviewImageItem(BaseModel):
    image_name: str
    image_id: int
    image_type: str


class ScReviewImagesByDefectItem(BaseModel):
    defect_id: str
    review_images: list[ScReviewImageItem]


class ScInspectionReviewImagesResponse(BaseModel):
    items: list[ScReviewImagesByDefectItem]
    total: int


class ScSampleTableSort(BaseModel):
    field: str
    direction: Literal["asc", "desc"]


class ScSampleTableSetFilter(BaseModel):
    operator: Literal["in", "not_in"]
    values: list[float | str] = Field(min_length=1)


class ScSampleTableRangeFilter(BaseModel):
    operator: Literal["between"]
    min: float
    max: float


class ScSampleTableRowsRequest(BaseModel):
    defect_ids: list[str] = Field(default_factory=list)
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=100, ge=1, le=10000)
    anchor: str | None = None
    limit: int = Field(default=100, ge=1, le=50_000)
    filter: dict[str, ScSampleTableSetFilter | ScSampleTableRangeFilter] | None = None
    sort: ScSampleTableSort | None = None
    reticle_x_die_count: int = Field(default=10, ge=1)
    reticle_y_die_count: int = Field(default=10, ge=1)
    reticle_x_die_shift: int = 0
    reticle_y_die_shift: int = 0


class ScSampleTableRow(BaseModel):
    defect_id: str
    rough_bin: int
    class_number: int
    test_id: int
    wafer_x: int
    wafer_y: int
    index_x: int
    index_y: int
    adder: int
    cluster_id: int | None = None
    die_x: int
    die_y: int
    reticle_x: int
    reticle_y: int
    size_x: int
    size_y: int
    size_d: int
    area: int
    final_bin: int
    manual_bin: int
    kill_ratio: float | None = None


class ScReclassifySampleTableRow(ScSampleTableRow):
    annotation_label: str | None = None
    prediction_label: str | None = None
    prediction_confidence: float | None = None


class ScSampleTableRowsResponse(BaseModel):
    items: list[ScSampleTableRow]
    total: int
    next_anchor: str | None = None


class ScReclassifySampleTableRowsResponse(BaseModel):
    items: list[ScReclassifySampleTableRow]
    total: int
    next_anchor: str | None = None


class ScBoxFilterRequest(BaseModel):
    mode: Literal["wafer", "die", "reticle"]
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    reticle_x_die_count: int = Field(default=3, ge=1)
    reticle_y_die_count: int = Field(default=5, ge=1)
    reticle_x_die_shift: int = 0
    reticle_y_die_shift: int = 0
    filter: dict[str, ScSampleTableSetFilter | ScSampleTableRangeFilter] | None = None


class ScBoxFilterResponse(BaseModel):
    defect_ids: list[str]
    total: int


class ScImportRequest(BaseModel):
    source_inspection_time: str
    source_wafer_key: int
    dataset_name: str = Field(..., min_length=1)
    storage_mode: str = "file_shard_sparse"
    filters: dict | None = None
    label_space: list[str] = []
    max_rows: int | None = None

    @field_validator("storage_mode")
    @classmethod
    def validate_storage_mode(cls, v: str) -> str:
        if v != "file_shard_sparse":
            raise ValueError(f"storage_mode must be file_shard_sparse, got: {v}")
        return v


class ScImportResponse(BaseModel):
    status: str
    dataset_id: str = ""
    imported_count: int = 0
    error: str | None = None


class ScAnnotationItem(BaseModel):
    defect_id: str
    label: str
    annotator: str = "platform-user"


class ScBulkAnnotationRequest(BaseModel):
    annotations: list[ScAnnotationItem]


class ScBulkAnnotationResponse(BaseModel):
    created: int


class ScFilterParams(BaseModel):
    """Filter and grouping parameters for SC plot-points endpoints.

    All fields are optional — when omitted no filtering is applied.
    List fields accept exploded query format: ``?class_numbers=1&class_numbers=2``.
    """

    class_numbers: list[int] | None = None
    rough_bins: list[int] | None = None
    predictions: list[str] | None = None
    annotations: list[str] | None = None
    test_ids: list[int] | None = None
    adders: list[int] | None = None
    cluster_ids: list[int] | None = None
    legend_group_by: str | None = None
    sample_filter: (
        dict[str, ScSampleTableSetFilter | ScSampleTableRangeFilter] | None
    ) = None
