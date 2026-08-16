from __future__ import annotations

from typing import Protocol

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
from app.modules.dataset_collections.domain.repository import (
    CollectionSortField,
    SortDirection,
)


class CollectionDatasetUsagePort(Protocol):
    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool: ...


class DatasetCollectionRevisionReaderPort(Protocol):
    async def get_revision(
        self, collection_id: str, revision_id: str, org_id: str
    ) -> DatasetCollectionRevision: ...


class CollectionPredictionAutomationPort(Protocol):
    async def predict_new_members(
        self,
        collection_id: str,
        snapshot_id: str,
        org_id: str,
        actor_id: str,
    ) -> CollectionPredictionBatch | None: ...

    async def list_coverage(
        self,
        collection_id: str,
        org_id: str,
        *,
        snapshot_id: str | None = None,
    ) -> list[CollectionPredictionCoverage]: ...

    async def get_batch(
        self,
        batch_id: str,
        org_id: str,
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]: ...


class CollectionModelManagementPort(CollectionPredictionAutomationPort, Protocol):
    async def set_default_model(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_binding_version: int,
        model_id: str | None,
    ) -> DatasetCollection: ...

    async def create_reconciliation_batch(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        snapshot_id: str,
        expected_default_model_id: str,
        request_id: str,
        dataset_ids: tuple[str, ...],
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]: ...

    async def retry_batch(
        self,
        batch_id: str,
        org_id: str,
        *,
        actor_id: str,
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]: ...

    async def list_batches(
        self,
        collection_id: str,
        org_id: str,
    ) -> list[
        tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]
    ]: ...


class CollectionSnapshotPublishingPort(Protocol):
    async def create_revision(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision: ...

    async def create_revision_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision: ...


class CollectionAutomationAdmissionPort(Protocol):
    """Internal Collection mutation boundary for authenticated org automations.

    HTTP routes keep creator-only manual mutation semantics. This port verifies
    collection/org identity and optimistic definition versions while preserving
    the triggering actor in audit fields.
    """

    async def get_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection: ...

    async def list_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]: ...

    async def admit_members_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def unlink_member_for_automation(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def publish_snapshot_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision: ...


class DatasetCollectionManagementPort(
    CollectionDatasetUsagePort, DatasetCollectionRevisionReaderPort, Protocol
):
    async def create_collection(
        self,
        *,
        org_id: str,
        created_by: str,
        name: str,
        description: str,
        target_view_id: str,
        duplicate_policy: str,
        missing_data_policy: str,
    ) -> DatasetCollection: ...

    async def list_collections(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
        creator_id: str | None = None,
        query: str | None = None,
        sort_by: CollectionSortField = "updated_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[DatasetCollection], int]: ...

    async def get_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection: ...

    async def get_snapshot_update_status(
        self, collection_id: str, org_id: str
    ) -> CollectionSnapshotUpdateStatus: ...

    async def refresh_snapshot(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> CollectionSnapshotRefreshResult: ...

    async def update_collection(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        name: str | None,
        description: str | None,
    ) -> DatasetCollection: ...

    async def delete_collection(
        self, collection_id: str, org_id: str, *, actor_id: str
    ) -> None: ...

    async def list_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]: ...

    async def link_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def unlink_member(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def replace_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def create_revision(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision: ...

    async def list_revisions(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionRevision]: ...
