from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field, JsonValue

from app.modules.source_discovery.domain.conditions import condition_to_json
from app.modules.source_discovery.domain.models import (
    DiscoveryExecution,
    DiscoveryRunItem,
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
    ImportProfileVersion,
    MembershipRule,
    MembershipRuleVersion,
    MembershipSuppression,
    SourceConnector,
    SourceEstimate,
    SourceFilterField,
    SourceProviderDescriptor,
    SourceRecord,
)


class FilterPredicateRequest(BaseModel):
    kind: Literal["predicate"] = "predicate"
    field: str = Field(min_length=1, max_length=128)
    operator: FilterOperator
    value: JsonValue

    def to_domain(self) -> FilterPredicate:
        return FilterPredicate(
            field=self.field,
            operator=self.operator,
            value=cast(object, self.value),
        )


class FilterGroupRequest(BaseModel):
    kind: Literal["group"] = "group"
    combinator: FilterCombinator
    children: list[
        Annotated[
            "FilterPredicateRequest | FilterGroupRequest",
            Field(discriminator="kind"),
        ]
    ]

    def to_domain(self) -> FilterGroup:
        return FilterGroup(
            combinator=self.combinator,
            children=tuple(child.to_domain() for child in self.children),
        )


FilterGroupRequest.model_rebuild()


class SourceFilterFieldResponse(BaseModel):
    key: str
    label: str
    field_type: str
    operators: list[str]

    @classmethod
    def from_domain(cls, value: SourceFilterField) -> SourceFilterFieldResponse:
        return cls(
            key=value.key,
            label=value.label,
            field_type=value.field_type.value,
            operators=[operator.value for operator in value.operators],
        )


class SourceProviderDescriptorResponse(BaseModel):
    provider_id: str
    display_name: str
    fields: list[SourceFilterFieldResponse]
    backfill_time_field: str | None
    max_condition_depth: int
    max_condition_nodes: int

    @classmethod
    def from_domain(
        cls, value: SourceProviderDescriptor
    ) -> SourceProviderDescriptorResponse:
        return cls(
            provider_id=value.provider_id,
            display_name=value.display_name,
            fields=[
                SourceFilterFieldResponse.from_domain(item) for item in value.fields
            ],
            backfill_time_field=value.backfill_time_field,
            max_condition_depth=value.max_condition_depth,
            max_condition_nodes=value.max_condition_nodes,
        )


class CreateSourceConnectorRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, JsonValue]


class SourceConnectorResponse(BaseModel):
    id: str
    org_id: str
    provider_id: str
    name: str
    enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: SourceConnector) -> SourceConnectorResponse:
        return cls(
            id=value.id,
            org_id=value.org_id,
            provider_id=value.provider_id,
            name=value.name,
            enabled=value.enabled,
            created_by=value.created_by,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )


class CreateImportProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    settings: dict[str, JsonValue]
    max_records_per_run: int = Field(gt=0)
    max_rows_per_dataset: int = Field(gt=0)


class ImportProfileVersionResponse(BaseModel):
    id: str
    profile_key: str
    version: int
    org_id: str
    connector_id: str
    name: str
    settings: dict[str, JsonValue]
    max_records_per_run: int
    max_rows_per_dataset: int
    created_by: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: ImportProfileVersion) -> ImportProfileVersionResponse:
        return cls(
            id=value.id,
            profile_key=value.profile_key,
            version=value.version,
            org_id=value.org_id,
            connector_id=value.connector_id,
            name=value.name,
            settings=cast(dict[str, JsonValue], value.settings),
            max_records_per_run=value.max_records_per_run,
            max_rows_per_dataset=value.max_rows_per_dataset,
            created_by=value.created_by,
            created_at=value.created_at,
        )


class CreateMembershipRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    connector_id: str = Field(min_length=1, max_length=64)
    import_profile_version_id: str = Field(min_length=1, max_length=64)
    condition: FilterGroupRequest


class CreateMembershipRuleVersionRequest(BaseModel):
    connector_id: str = Field(min_length=1, max_length=64)
    import_profile_version_id: str = Field(min_length=1, max_length=64)
    condition: FilterGroupRequest


class MembershipRuleVersionResponse(BaseModel):
    id: str
    rule_id: str
    version: int
    connector_id: str
    import_profile_version_id: str
    condition: dict[str, JsonValue]
    created_by: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: MembershipRuleVersion) -> MembershipRuleVersionResponse:
        return cls(
            id=value.id,
            rule_id=value.rule_id,
            version=value.version,
            connector_id=value.connector_id,
            import_profile_version_id=value.import_profile_version_id,
            condition=cast(dict[str, JsonValue], condition_to_json(value.condition)),
            created_by=value.created_by,
            created_at=value.created_at,
        )


class MembershipRuleResponse(BaseModel):
    id: str
    org_id: str
    collection_id: str
    name: str
    status: str
    active_version_id: str
    activated_at: datetime
    created_by: str
    created_at: datetime
    updated_at: datetime
    active_version: MembershipRuleVersionResponse

    @classmethod
    def from_domain(
        cls, rule: MembershipRule, version: MembershipRuleVersion
    ) -> MembershipRuleResponse:
        return cls(
            id=rule.id,
            org_id=rule.org_id,
            collection_id=rule.collection_id,
            name=rule.name,
            status=rule.status,
            active_version_id=rule.active_version_id,
            activated_at=rule.activated_at,
            created_by=rule.created_by,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            active_version=MembershipRuleVersionResponse.from_domain(version),
        )


class RunLiveDiscoveryRequest(BaseModel):
    as_of_utc: datetime


class BackfillRangeRequest(BaseModel):
    start_utc: datetime
    end_utc: datetime
    timezone: str = Field(min_length=1, max_length=128)


class BackfillPreviewRequest(BackfillRangeRequest):
    representative_limit: int = Field(ge=1, le=20)


class SourceRecordResponse(BaseModel):
    record_key: str
    source_version: str | None
    observed_at: datetime
    display_name: str
    attributes: dict[str, JsonValue]

    @classmethod
    def from_domain(cls, value: SourceRecord) -> SourceRecordResponse:
        return cls(
            record_key=value.record_key,
            source_version=value.source_version,
            observed_at=value.observed_at,
            display_name=value.display_name,
            attributes=cast(dict[str, JsonValue], value.attributes),
        )


class BackfillPreviewResponse(BaseModel):
    as_of_utc: datetime
    matched_count: int
    representative_records: list[SourceRecordResponse]

    @classmethod
    def from_domain(cls, value: SourceEstimate) -> BackfillPreviewResponse:
        return cls(
            as_of_utc=value.as_of_utc,
            matched_count=value.matched_count,
            representative_records=[
                SourceRecordResponse.from_domain(record)
                for record in value.representative_records
            ],
        )


class DiscoveryRunItemResponse(BaseModel):
    id: str
    source_record_key: str
    source_version: str | None
    observed_at: datetime
    status: str
    dataset_id: str | None
    member_id: str | None
    error_detail: str | None

    @classmethod
    def from_domain(cls, value: DiscoveryRunItem) -> DiscoveryRunItemResponse:
        return cls(
            id=value.id,
            source_record_key=value.source_record_key,
            source_version=value.source_version,
            observed_at=value.observed_at,
            status=value.status,
            dataset_id=value.dataset_id,
            member_id=value.member_id,
            error_detail=value.error_detail,
        )


class DiscoveryRunResponse(BaseModel):
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
    timezone: str | None
    parent_run_id: str | None
    snapshot_revision_id: str | None
    stats: dict[str, int]
    error_detail: str | None
    created_by: str
    created_at: datetime
    completed_at: datetime | None
    items: list[DiscoveryRunItemResponse]

    @classmethod
    def from_domain(cls, value: DiscoveryExecution) -> DiscoveryRunResponse:
        run = value.run
        return cls(
            id=run.id,
            org_id=run.org_id,
            collection_id=run.collection_id,
            rule_id=run.rule_id,
            rule_version_id=run.rule_version_id,
            kind=run.kind,
            status=run.status,
            as_of_utc=run.as_of_utc,
            range_start_utc=run.range_start_utc,
            range_end_utc=run.range_end_utc,
            timezone=run.timezone_name,
            parent_run_id=run.parent_run_id,
            snapshot_revision_id=run.snapshot_revision_id,
            stats=run.stats,
            error_detail=run.error_detail,
            created_by=run.created_by,
            created_at=run.created_at,
            completed_at=run.completed_at,
            items=[DiscoveryRunItemResponse.from_domain(item) for item in value.items],
        )


class SuppressSourceMemberRequest(BaseModel):
    connector_id: str = Field(min_length=1, max_length=64)
    source_record_key: str = Field(min_length=1, max_length=512)
    expected_definition_version: int = Field(ge=0)
    reason: str = Field(max_length=2000)


class MembershipSuppressionResponse(BaseModel):
    id: str
    collection_id: str
    connector_id: str
    source_record_key: str
    reason: str
    created_by: str
    created_at: datetime
    cleared_by: str | None
    cleared_at: datetime | None

    @classmethod
    def from_domain(cls, value: MembershipSuppression) -> MembershipSuppressionResponse:
        return cls(
            id=value.id,
            collection_id=value.collection_id,
            connector_id=value.connector_id,
            source_record_key=value.source_record_key,
            reason=value.reason,
            created_by=value.created_by,
            created_at=value.created_at,
            cleared_by=value.cleared_by,
            cleared_at=value.cleared_at,
        )
