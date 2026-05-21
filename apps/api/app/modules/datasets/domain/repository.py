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

    async def update_dataset_task_spec(
        self,
        dataset_id: str,
        task_spec: dict,
    ) -> Dataset | None: ...
