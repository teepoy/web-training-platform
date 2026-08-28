from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


@dataclass(frozen=True, slots=True)
class DatasetCollection:
    id: str
    org_id: str
    name: str
    description: str
    target_view_id: str
    target_view_contract: str
    target_schema_version: str
    duplicate_policy: str
    missing_data_policy: str
    definition_version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    creator_name: str = ""
    default_model_id: str | None = None
    model_binding_version: int = 0


@dataclass(frozen=True, slots=True)
class NewCollectionMember:
    source_dataset_id: str
    position: int
    filter_spec: dict[str, object] = field(default_factory=dict)
    label_mapping: dict[str, str] = field(default_factory=dict)
    sampling_spec: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetCollectionMember:
    id: str
    collection_id: str
    source_dataset_id: str
    position: int
    linked_definition_version: int
    unlinked_definition_version: int | None
    filter_spec: dict[str, object]
    label_mapping: dict[str, str]
    sampling_spec: dict[str, object]
    linked_by: str
    linked_at: datetime
    unlinked_by: str | None
    unlinked_at: datetime | None


@dataclass(frozen=True, slots=True)
class DatasetCollectionRevision:
    id: str
    collection_id: str
    revision_number: int
    definition_version: int
    definition_hash: str
    target_view_id: str
    target_view_contract: str
    target_schema_version: str
    status: str
    source_snapshot: tuple[dict[str, object], ...]
    row_count: int | None
    label_counts: dict[str, int]
    manifest_uri: str | None
    provenance_uri: str | None
    trigger_kind: str
    trigger_ref: str | None
    created_by: str
    created_at: datetime
    error_code: str | None
    error_detail: str | None
    manifest_format: str = "legacy_materialized_v1"
    source_resolution: str = "legacy_materialized"
    reproducibility_capability: bool = True


@dataclass(frozen=True, slots=True)
class CollectionSnapshotMemberUpdate:
    member_id: str
    dataset_id: str
    observed_dataset_revision_id: str | None
    observed_dataset_revision_number: int | None
    current_dataset_revision_id: str | None
    current_dataset_revision_number: int | None
    update_available: bool


@dataclass(frozen=True, slots=True)
class CollectionSnapshotUpdateStatus:
    snapshot_id: str | None
    snapshot_revision_number: int | None
    update_available: bool
    outdated_member_count: int
    members: tuple[CollectionSnapshotMemberUpdate, ...]


@dataclass(frozen=True, slots=True)
class CollectionSnapshotRefreshResult:
    outcome: Literal["refreshed", "unchanged"]
    snapshot: DatasetCollectionRevision


class PredictionCoverageStatus(str, Enum):
    CURRENT = "current"
    MODEL_MISMATCH = "model_mismatch"
    DATA_OUTDATED = "data_outdated"
    NOT_PREDICTED = "not_predicted"


@dataclass(frozen=True, slots=True)
class CollectionPredictionObservation:
    member_id: str | None
    dataset_id: str
    prediction_job_id: str
    dataset_revision_id: str | None
    model_id: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CollectionPredictionCoverage:
    member_id: str
    dataset_id: str
    expected_dataset_revision_id: str
    status: PredictionCoverageStatus
    default_model_id: str | None
    latest_prediction_job_id: str | None
    latest_prediction_model_id: str | None
    latest_prediction_dataset_revision_id: str | None
    latest_prediction_status: str | None
    active_prediction_job_id: str | None
    active_prediction_status: str | None


@dataclass(frozen=True, slots=True)
class CollectionPredictionBatch:
    id: str
    collection_id: str
    collection_revision_id: str
    model_id: str
    kind: str
    request_id: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CollectionPredictionBatchItem:
    id: str
    batch_id: str
    member_id: str
    dataset_id: str
    dataset_revision_id: str
    prediction_job_id: str | None
    status: str
    attempt_count: int
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
