from __future__ import annotations

from typing import Protocol

from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)


class CollectionDatasetUsagePort(Protocol):
    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool: ...


class DatasetCollectionRevisionReaderPort(Protocol):
    async def get_revision(
        self, collection_id: str, revision_id: str, org_id: str
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
    ) -> tuple[list[DatasetCollection], int]: ...

    async def get_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection: ...

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
