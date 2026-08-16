from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DatasetRevisionOperation(str, Enum):
    INITIAL_IMPORT = "initial_import"
    REIMPORT = "reimport"
    ANNOTATION_SYNC = "annotation_sync"
    BATCH_EDIT = "batch_edit"
    LEGACY_BASELINE = "legacy_baseline"


@dataclass(frozen=True)
class DatasetRevision:
    id: str
    dataset_id: str
    revision_number: int
    manifest_uri: str
    operation: DatasetRevisionOperation
    created_by: str
    created_at: datetime
    is_reproducible: bool = False
    provenance: dict[str, object] = field(default_factory=dict)
    operation_ref: str | None = None
