from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SourceFieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    IS_NULL = "is_null"


class FilterCombinator(StrEnum):
    ALL = "all"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class SourceFilterField:
    key: str
    label: str
    field_type: SourceFieldType
    operators: tuple[FilterOperator, ...]


@dataclass(frozen=True, slots=True)
class SourceProviderDescriptor:
    provider_id: str
    display_name: str
    fields: tuple[SourceFilterField, ...]
    backfill_time_field: str | None
    max_condition_depth: int
    max_condition_nodes: int


@dataclass(frozen=True, slots=True)
class FilterPredicate:
    field: str
    operator: FilterOperator
    value: object | None


@dataclass(frozen=True, slots=True)
class FilterGroup:
    combinator: FilterCombinator
    children: tuple[FilterNode, ...]


FilterNode = FilterPredicate | FilterGroup


@dataclass(frozen=True, slots=True)
class SourceConnector:
    id: str
    org_id: str
    provider_id: str
    name: str
    config: dict[str, object]
    enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImportProfileVersion:
    id: str
    profile_key: str
    version: int
    org_id: str
    connector_id: str
    name: str
    settings: dict[str, object]
    max_records_per_run: int
    max_rows_per_dataset: int
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipRule:
    id: str
    org_id: str
    collection_id: str
    name: str
    status: str
    active_version_id: str
    activated_at: datetime
    live_cursor: dict[str, object] | None
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipRuleVersion:
    id: str
    rule_id: str
    version: int
    connector_id: str
    import_profile_version_id: str
    condition: FilterGroup
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SourceRecord:
    record_key: str
    source_version: str | None
    observed_at: datetime
    display_name: str
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class SourceDiscoveryBatch:
    records: tuple[SourceRecord, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class SourceEstimate:
    as_of_utc: datetime
    matched_count: int
    representative_records: tuple[SourceRecord, ...]


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    dataset_id: str
    dataset_name: str
    imported_count: int


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    id: str
    org_id: str
    collection_id: str
    rule_id: str
    rule_version_id: str
    kind: str
    status: str
    as_of_utc: datetime
    range_start_utc: datetime | None
    range_end_utc: datetime | None
    timezone_name: str | None
    parent_run_id: str | None
    snapshot_revision_id: str | None
    stats: dict[str, int]
    error_detail: str | None
    created_by: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscoveryRunItem:
    id: str
    run_id: str
    connector_id: str
    source_record_key: str
    source_version: str | None
    observed_at: datetime
    source_payload: dict[str, object]
    status: str
    dataset_id: str | None
    member_id: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImportReceipt:
    id: str
    collection_id: str
    connector_id: str
    source_record_key: str
    source_version: str | None
    import_profile_version_id: str
    status: str
    dataset_id: str | None
    attempts: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class SourceMembership:
    id: str
    collection_id: str
    connector_id: str
    source_record_key: str
    source_version: str | None
    dataset_id: str
    member_id: str
    admitted_by_rule_id: str
    admitted_by_run_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipSuppression:
    id: str
    collection_id: str
    connector_id: str
    source_record_key: str
    created_by: str
    created_at: datetime
    reason: str = ""
    cleared_by: str | None = None
    cleared_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryExecution:
    run: DiscoveryRun
    items: tuple[DiscoveryRunItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CollectionDiscoveryPoll:
    as_of_utc: datetime
    executions: tuple[DiscoveryExecution, ...]
