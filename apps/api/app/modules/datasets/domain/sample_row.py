from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SampleRowImageRef:
    """Embedded image reference within a sparse v2 sample row."""

    image_id: str
    role: str
    content_type: str
    filename: str
    bytes_: bytes | None = None
    access_url: str = ""


@dataclass
class PredictionResult:
    """Domain type representing a single prediction for a sample.

    Carries the predicted label, optional confidence/scores, and
    provenance metadata (model, job, target).
    """

    sample_id: str
    predicted_label: str
    confidence: float | None = None
    all_scores: dict[str, float] | None = None
    model_id: str | None = None
    target: str | None = None
    model_version: str | None = None
    job_id: str | None = None
    error: str | None = None


@dataclass
class SampleRow:
    """Canonical domain row for a single sample in a dataset."""

    sample_id: str
    dataset_id: str
    image_uris: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    images: list[SampleRowImageRef] | None = None
    embedded_bytes: dict[str, bytes] | None = None
    label: str | None = None
    latest_label: str | None = None
    annotation_id: str | None = None
    annotation_value: dict | list | None = None
    latest_prediction: dict[str, Any] | None = None
    ls_task_id: int | None = None
    created_at: datetime | None = None


@dataclass
class BulkImageRef:
    """Image payload for bulk import — carries raw bytes (nullable)."""

    image_id: str
    role: str
    bytes_: bytes | None = None
    image_type: str = ""
    content_type: str = "image/png"
    filename: str = ""
    source_uri: str | None = None


@dataclass
class BulkSampleRow:
    """Bulk-importable sample row with embedded image bytes.

    Designed for ``write_samples``: each row carries a sample_id,
    optional images/metadata/label, and an ``extra`` bag for
    storage-specific payload.
    """

    sample_id: str
    image_uris: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    images: list[BulkImageRef] | None = None
