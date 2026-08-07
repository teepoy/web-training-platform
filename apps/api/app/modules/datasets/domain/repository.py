from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import ArtifactRef, Dataset


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
    ) -> list[Dataset]: ...

    async def list_dataset_names(
        self,
        dataset_ids: list[str],
        org_id: str | None = None,
    ) -> dict[str, str]: ...

    async def count_datasets(self, org_id: str | None = None) -> int: ...

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

    async def rename_dataset(
        self,
        dataset_id: str,
        *,
        name: str,
        org_id: str | None = None,
    ) -> Dataset | None: ...


class ArtifactLookupRepository(Protocol):
    async def get_artifact(self, artifact_id: str) -> ArtifactRef | None: ...
