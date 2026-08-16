from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.dataset_collections.domain.models import (
    CollectionPredictionBatch,
    CollectionPredictionBatchItem,
    CollectionPredictionCoverage,
    CollectionSnapshotRefreshResult,
    CollectionSnapshotUpdateStatus,
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateDatasetCollectionRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(max_length=10000)
    target_view_id: str = Field(min_length=1, max_length=128)
    duplicate_policy: Literal["keep_all"]
    missing_data_policy: Literal["fail"]


class UpdateDatasetCollectionRequest(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


class UpdateCollectionDefaultModelRequest(StrictRequest):
    expected_binding_version: int = Field(ge=0)
    model_id: str | None = Field(default=None, min_length=1, max_length=64)


class CreateCollectionPredictionBatchRequest(StrictRequest):
    snapshot_id: str = Field(min_length=1, max_length=64)
    expected_default_model_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=128)
    dataset_ids: list[str] = Field(min_length=1)


class DatasetCollectionMemberInput(StrictRequest):
    source_dataset_id: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=0)
    filter_spec: dict[str, object] = Field(default_factory=dict)
    label_mapping: dict[str, str] = Field(default_factory=dict)
    sampling_spec: dict[str, object] = Field(default_factory=dict)

    def to_domain(self) -> NewCollectionMember:
        return NewCollectionMember(
            source_dataset_id=self.source_dataset_id,
            position=self.position,
            filter_spec=self.filter_spec,
            label_mapping=self.label_mapping,
            sampling_spec=self.sampling_spec,
        )


class LinkDatasetCollectionMembersRequest(StrictRequest):
    expected_definition_version: int = Field(ge=0)
    members: list[DatasetCollectionMemberInput] = Field(min_length=1)


class ReplaceDatasetCollectionMembersRequest(StrictRequest):
    expected_definition_version: int = Field(ge=0)
    members: list[DatasetCollectionMemberInput]


class CreateDatasetCollectionRevisionRequest(StrictRequest):
    expected_definition_version: int = Field(ge=1)


class DatasetCollectionResponse(BaseModel):
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
    default_model_id: str | None
    model_binding_version: int

    @classmethod
    def from_domain(cls, collection: DatasetCollection) -> DatasetCollectionResponse:
        return cls(**asdict(collection))


class DatasetCollectionMemberResponse(BaseModel):
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

    @classmethod
    def from_domain(
        cls, member: DatasetCollectionMember
    ) -> DatasetCollectionMemberResponse:
        return cls(**asdict(member))


class DatasetCollectionMembershipResponse(BaseModel):
    collection: DatasetCollectionResponse
    members: list[DatasetCollectionMemberResponse]

    @classmethod
    def from_domain(
        cls,
        collection: DatasetCollection,
        members: list[DatasetCollectionMember],
    ) -> DatasetCollectionMembershipResponse:
        return cls(
            collection=DatasetCollectionResponse.from_domain(collection),
            members=[
                DatasetCollectionMemberResponse.from_domain(member)
                for member in members
            ],
        )


class DatasetCollectionRevisionResponse(BaseModel):
    id: str
    collection_id: str
    revision_number: int
    definition_version: int
    definition_hash: str
    target_view_id: str
    target_view_contract: str
    target_schema_version: str
    status: str
    source_snapshot: list[dict[str, object]]
    row_count: int | None
    label_counts: dict[str, int]
    manifest_uri: str | None
    provenance_uri: str | None
    manifest_format: str
    source_resolution: str
    reproducibility_capability: bool
    trigger_kind: str
    trigger_ref: str | None
    created_by: str
    created_at: datetime
    error_code: str | None
    error_detail: str | None

    @classmethod
    def from_domain(
        cls, revision: DatasetCollectionRevision
    ) -> DatasetCollectionRevisionResponse:
        return cls(
            id=revision.id,
            collection_id=revision.collection_id,
            revision_number=revision.revision_number,
            definition_version=revision.definition_version,
            definition_hash=revision.definition_hash,
            target_view_id=revision.target_view_id,
            target_view_contract=revision.target_view_contract,
            target_schema_version=revision.target_schema_version,
            status=revision.status,
            source_snapshot=list(revision.source_snapshot),
            row_count=revision.row_count,
            label_counts=revision.label_counts,
            manifest_uri=revision.manifest_uri,
            provenance_uri=revision.provenance_uri,
            manifest_format=revision.manifest_format,
            source_resolution=revision.source_resolution,
            reproducibility_capability=revision.reproducibility_capability,
            trigger_kind=revision.trigger_kind,
            trigger_ref=revision.trigger_ref,
            created_by=revision.created_by,
            created_at=revision.created_at,
            error_code=revision.error_code,
            error_detail=revision.error_detail,
        )


class CollectionSnapshotMemberUpdateResponse(BaseModel):
    member_id: str
    dataset_id: str
    observed_dataset_revision_id: str | None
    observed_dataset_revision_number: int | None
    current_dataset_revision_id: str | None
    current_dataset_revision_number: int | None
    update_available: bool


class CollectionSnapshotUpdateStatusResponse(BaseModel):
    snapshot_id: str | None
    snapshot_revision_number: int | None
    update_available: bool
    outdated_member_count: int
    members: list[CollectionSnapshotMemberUpdateResponse]

    @classmethod
    def from_domain(
        cls, status: CollectionSnapshotUpdateStatus
    ) -> CollectionSnapshotUpdateStatusResponse:
        return cls(
            snapshot_id=status.snapshot_id,
            snapshot_revision_number=status.snapshot_revision_number,
            update_available=status.update_available,
            outdated_member_count=status.outdated_member_count,
            members=[
                CollectionSnapshotMemberUpdateResponse(**asdict(member))
                for member in status.members
            ],
        )


class CollectionSnapshotRefreshResponse(BaseModel):
    outcome: Literal["refreshed", "unchanged"]
    snapshot: DatasetCollectionRevisionResponse

    @classmethod
    def from_domain(
        cls, result: CollectionSnapshotRefreshResult
    ) -> CollectionSnapshotRefreshResponse:
        return cls(
            outcome=result.outcome,
            snapshot=DatasetCollectionRevisionResponse.from_domain(result.snapshot),
        )


class DatasetCollectionErrorResponse(BaseModel):
    code: str
    detail: str


class CollectionPredictionCoverageResponse(BaseModel):
    member_id: str
    dataset_id: str
    expected_dataset_revision_id: str
    status: str
    default_model_id: str | None
    latest_prediction_job_id: str | None
    latest_prediction_model_id: str | None
    latest_prediction_dataset_revision_id: str | None
    latest_prediction_status: str | None
    active_prediction_job_id: str | None
    active_prediction_status: str | None

    @classmethod
    def from_domain(
        cls, coverage: CollectionPredictionCoverage
    ) -> CollectionPredictionCoverageResponse:
        return cls(**asdict(coverage))


class CollectionPredictionBatchItemResponse(BaseModel):
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

    @classmethod
    def from_domain(
        cls, item: CollectionPredictionBatchItem
    ) -> CollectionPredictionBatchItemResponse:
        return cls(**asdict(item))


class CollectionPredictionBatchResponse(BaseModel):
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
    items: list[CollectionPredictionBatchItemResponse]

    @classmethod
    def from_domain(
        cls,
        batch: CollectionPredictionBatch,
        items: list[CollectionPredictionBatchItem],
    ) -> CollectionPredictionBatchResponse:
        return cls(
            **asdict(batch),
            items=[
                CollectionPredictionBatchItemResponse.from_domain(item)
                for item in items
            ],
        )
