from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.shared.api.schemas import ArtifactRef, CreatorSummary, Dataset

DatasetSortField = Literal["name", "dataset_type", "creator", "created_at"]
SortDirection = Literal["asc", "desc"]


class DatasetRepository(Protocol):
    async def create_dataset(
        self,
        dataset: Dataset,
        org_id: str | None = None,
    ) -> Dataset: ...

    async def list_datasets(
        self,
        org_id: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str | None = None,
        creator_id: str | None = None,
        sort_by: DatasetSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> list[Dataset]: ...

    async def list_dataset_creators(
        self,
        org_id: str | None = None,
    ) -> list[CreatorSummary]: ...

    async def list_dataset_names(
        self,
        dataset_ids: list[str],
        org_id: str | None = None,
    ) -> dict[str, str]: ...

    async def list_datasets_by_ids(
        self,
        dataset_ids: list[str],
        org_id: str | None = None,
    ) -> list[Dataset]: ...

    async def list_datasets_for_sc_inspections(
        self,
        inspection_times: Sequence[str],
        org_id: str | None = None,
    ) -> list[Dataset]: ...

    async def count_datasets(
        self,
        org_id: str | None = None,
        *,
        query: str | None = None,
        creator_id: str | None = None,
    ) -> int: ...

    async def get_dataset(
        self,
        dataset_id: str,
        org_id: str | None = None,
    ) -> Dataset | None: ...

    async def delete_dataset(
        self,
        dataset_id: str,
        org_id: str | None = None,
    ) -> bool: ...

    async def update_dataset_meta(
        self,
        dataset_id: str,
        meta_update: dict,
        *,
        org_id: str | None = None,
    ) -> Dataset | None: ...

    async def existing_sample_ids(self, sample_ids: set[str]) -> set[str]: ...

    async def rename_dataset(
        self,
        dataset_id: str,
        *,
        name: str,
        org_id: str | None = None,
    ) -> Dataset | None: ...


class ArtifactLookupRepository(Protocol):
    async def get_artifact(self, artifact_id: str) -> ArtifactRef | None: ...


class DatasetRevisionRepository(Protocol):
    async def publish_revision(
        self,
        *,
        revision_id: str,
        dataset_id: str,
        org_id: str,
        manifest_uri: str,
        provenance: dict[str, object],
        operation: DatasetRevisionOperation,
        operation_ref: str | None,
        created_by: str,
    ) -> DatasetRevision: ...

    async def get_current_revision(
        self,
        dataset_id: str,
        org_id: str,
    ) -> DatasetRevision | None: ...

    async def list_current_revisions(
        self,
        dataset_ids: tuple[str, ...],
        org_id: str,
    ) -> dict[str, DatasetRevision]: ...

    async def get_revision(
        self,
        dataset_id: str,
        revision_id: str,
        org_id: str,
    ) -> DatasetRevision | None: ...

    async def list_revisions(
        self,
        dataset_id: str,
        org_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[DatasetRevision]: ...

    async def count_revisions(self, dataset_id: str, org_id: str) -> int: ...
