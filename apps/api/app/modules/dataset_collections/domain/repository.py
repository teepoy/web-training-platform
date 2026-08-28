from __future__ import annotations

from typing import Literal, Protocol

from app.shared.api.schemas import CreatorSummary

from app.modules.dataset_collections.domain.models import (
    CollectionPredictionBatch,
    CollectionPredictionBatchItem,
    CollectionPredictionObservation,
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)

CollectionSortField = Literal["name", "creator", "created_at", "updated_at"]
SortDirection = Literal["asc", "desc"]


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
        query: str | None = None,
        sort_by: CollectionSortField = "updated_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[DatasetCollection], int]: ...

    async def list_collection_creators(self, org_id: str) -> list[CreatorSummary]: ...

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

    async def set_default_model(
        self,
        collection_id: str,
        org_id: str,
        *,
        expected_binding_version: int,
        model_id: str | None,
    ) -> DatasetCollection: ...

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

    async def get_current_revision(
        self, collection_id: str, org_id: str
    ) -> DatasetCollectionRevision | None: ...

    async def list_prediction_observations(
        self,
        collection_id: str,
        org_id: str,
        dataset_ids: tuple[str, ...],
    ) -> list[CollectionPredictionObservation]: ...

    async def create_or_get_prediction_batch(
        self,
        batch: CollectionPredictionBatch,
        items: tuple[CollectionPredictionBatchItem, ...],
        org_id: str,
    ) -> tuple[
        CollectionPredictionBatch, list[CollectionPredictionBatchItem], bool
    ]: ...

    async def get_prediction_batch(
        self,
        batch_id: str,
        org_id: str,
    ) -> (
        tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]] | None
    ): ...

    async def list_prediction_batches(
        self,
        collection_id: str,
        org_id: str,
    ) -> list[
        tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]
    ]: ...

    async def update_prediction_batch_item(
        self,
        item_id: str,
        *,
        prediction_job_id: str | None,
        status: str,
        error_detail: str | None,
        increment_attempt: bool,
    ) -> CollectionPredictionBatchItem: ...

    async def update_prediction_batch_status(
        self,
        batch_id: str,
        status: str,
    ) -> None: ...

    async def next_revision_number(self, collection_id: str, org_id: str) -> int: ...

    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool: ...
