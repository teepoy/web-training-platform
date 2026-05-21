from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ColumnSchema(BaseModel):
    """Column name and type pair describing the dataset schema."""

    name: str
    type: str


class ShardEntry(BaseModel):
    """Metadata for a single payload shard stored in object storage."""

    shard_index: int
    uri: str
    row_count: int
    format: str = "parquet"
    checksum_sha256: str
    byte_size: int


class DatasetManifest(BaseModel):
    """Top-level manifest describing the shard layout of a dataset payload."""

    dataset_id: str
    storage_mode: str
    shard_count: int
    total_rows: int
    schema_columns: list[ColumnSchema] = Field(default_factory=list)
    shards: list[ShardEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SampleLocator(BaseModel):
    """Locates a single logical row within a shard-backed dataset payload."""

    dataset_id: str
    shard_index: int
    row_index: int
    upstream_item_id: str | None = None


class SparseRowIdentity(BaseModel):
    locator: SampleLocator

    @property
    def display_id(self) -> str:
        return f"{self.locator.shard_index}:{self.locator.row_index}"


# ---------------------------------------------------------------------------
# Sparse prediction result domain models
# ---------------------------------------------------------------------------


class SparsePredictionResult(BaseModel):
    """Row-level prediction for a single sample in a ``file_shard_sparse`` dataset.

    Each result is keyed by a :class:`SampleLocator` so that review /
    reclassify workflows can join the prediction back to the original
    shard row without needing a platform-global ``sample_id``.
    """

    locator: SampleLocator
    predicted_label: str
    confidence: float | None = None
    all_scores: dict[str, float] | None = None
    error: str | None = None


class SparsePredictionShard(BaseModel):
    """One shard's worth of prediction results.

    Mirrors the dataset shard layout 1:1 — input shard *i* produces
    prediction shard *i*, stored alongside each other in object storage.
    """

    shard_uri: str
    shard_index: int
    model_id: str
    model_version: str | None = None
    results: list[SparsePredictionResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SparsePredictionJobResult(BaseModel):
    """Top-level prediction job output for a ``file_shard_sparse`` dataset.

    Aggregates per-shard results into a single document so that any
    downstream consumer (review UI, reclassify flow, export) can
    discover all prediction shards without scanning object storage.
    """

    job_id: str
    dataset_id: str
    model_id: str
    model_version: str | None = None
    shards: list[SparsePredictionShard] = Field(default_factory=list)
    total_processed: int = 0
    total_successful: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
