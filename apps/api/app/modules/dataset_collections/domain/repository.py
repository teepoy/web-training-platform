from __future__ import annotations

from typing import Protocol

from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)


class DatasetCollectionRepository(Protocol):
    async def create_collection(
        self, collection: DatasetCollection
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
    ) -> DatasetCollection | None: ...

    async def update_collection(
        self,
        collection_id: str,
        org_id: str,
        *,
        name: str | None,
        description: str | None,
    ) -> DatasetCollection | None: ...

    async def delete_collection(
        self, collection_id: str, org_id: str
    ) -> tuple[str, ...] | None: ...

    async def list_active_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]: ...

    async def link_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def unlink_member(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def replace_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]: ...

    async def create_revision(
        self,
        revision: DatasetCollectionRevision,
        org_id: str,
        *,
        expected_definition_version: int,
    ) -> DatasetCollectionRevision: ...

    async def list_revisions(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionRevision]: ...

    async def get_revision(
        self, collection_id: str, revision_id: str, org_id: str
    ) -> DatasetCollectionRevision | None: ...

    async def next_revision_number(self, collection_id: str, org_id: str) -> int: ...

    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool: ...
