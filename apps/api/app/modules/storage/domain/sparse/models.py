"""Shared domain models for sparse (file-shard-backed) datasets.

These Pydantic models are the canonical contract for manifest structures,
shard metadata, sample locators, and prediction results.  Both API and
worker import them from ``app.modules.storage.domain.sparse`` — no ``apps.api``
cross-import needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class SparseIndexEntry(BaseModel):
    """Metadata for the compact Parquet sample-locator index."""

    uri: str
    row_count: int
    format: Literal["parquet"] = "parquet"
    checksum_sha256: str
    byte_size: int


class DatasetManifest(BaseModel):
    """Top-level manifest describing the shard layout of a dataset payload.

    The optional ``sample_index`` maps ``sample_id`` (or ``defect_id``
    where appropriate) to a :class:`SampleLocator`, enabling O(1) row
    lookups without full-shard scans.  Manifests without this key load
    with an empty dict — callers must fall back to scan-based lookup.

    ``schema_version`` records the data-source-specific shard schema
    version (e.g. ``"v2"`` for SC source shards).  ``None`` for legacy
    manifests that were written before version tracking was introduced.
    """

    dataset_id: str
    storage_mode: str
    shard_count: int
    total_rows: int
    schema_columns: list[ColumnSchema] = Field(default_factory=list)
    shards: list[ShardEntry] = Field(default_factory=list)
    sample_index: dict[str, SampleLocator] = Field(default_factory=dict)
    index: SparseIndexEntry | None = None
    manifest_version: Literal["v2", "v3"] = "v2"
    schema_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SampleLocator(BaseModel):
    """Locates a single logical row within a shard-backed dataset payload."""

    dataset_id: str
    shard_index: int
    row_index: int
    upstream_item_id: str | None = None


class SparseRowIdentity(BaseModel):
    """Identity wrapper for a sparse dataset row."""

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


# ---------------------------------------------------------------------------
# Runtime materialization models
# ---------------------------------------------------------------------------


class RuntimeMaterializationManifest(BaseModel):
    """Manifest describing a runtime-materialized dataset for train or predict.

    Captures identity, schema version, shard layout, and size metrics so
    that downstream consumers (reader, store, worker) can discover and
    validate materialized parquet payloads without scanning object storage.
    """

    purpose: Literal["train", "predict"]
    job_id: str
    org_id: str
    dataset_id: str
    view_id: str
    schema_version: str
    row_count: int
    byte_count: int
    shards: list[ShardEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RuntimeMaterializedRow(BaseModel):
    """Single row in a runtime-materialized parquet shard.

    Carries a sample identity, optional label, and one or more binary
    payload columns (image_bytes, defective_bytes, reference_bytes).
    At least one bytes field must be present — uri-only rows are rejected.
    """

    sample_id: str
    label: str | None = None
    image_bytes: bytes | None = None
    defective_bytes: bytes | None = None
    reference_bytes: bytes | None = None

    @model_validator(mode="after")
    def _check_at_least_one_bytes_field(self) -> RuntimeMaterializedRow:
        if (
            self.image_bytes is None
            and self.defective_bytes is None
            and self.reference_bytes is None
        ):
            raise ValueError(
                "At least one bytes field (image_bytes, defective_bytes, "
                "reference_bytes) is required"
            )
        return self
