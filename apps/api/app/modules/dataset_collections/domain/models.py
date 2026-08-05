from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
