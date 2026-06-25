from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import Dataset


class DatasetRepository(Protocol):
    async def create_dataset(
        self,
        dataset: Dataset,
        org_id: str | None = None,
    ) -> Dataset: ...

    async def list_datasets(self, org_id: str | None = None) -> list[Dataset]: ...

    async def count_samples_by_dataset(
        self,
        dataset_ids: list[str],
    ) -> dict[str, int]: ...

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
    ) -> Dataset | None: ...

    async def rename_dataset(
        self,
        dataset_id: str,
        *,
        name: str,
        org_id: str | None = None,
    ) -> Dataset | None: ...

    async def set_dataset_public(
        self,
        dataset_id: str,
        is_public: bool,
    ) -> bool: ...

    async def update_dataset_embed_config(
        self,
        dataset_id: str,
        embed_config: dict,
    ) -> None: ...
