from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class StorageProvider(Protocol):
    """Generic dataset storage operations contract."""

    async def create_dataset(
        self,
        *,
        name: str,
        dataset_type: str,
        view_types: list[str],
        label_space: list[str],
        org_id: str,
    ) -> dict: ...

    async def add_samples(self, dataset_id: str, samples: list[dict]) -> list[dict]: ...

    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[dict], int]: ...

    async def get_dataset(self, dataset_id: str) -> dict | None: ...

    async def delete_dataset(self, dataset_id: str) -> None: ...


class DatasetAdapter(Protocol[T]):
    """Per-type contract implemented in each subdomain (classification/ detection/ vqa).

    ``T`` is the dataset-type-specific Pydantic model (e.g. ``ClassificationDataset``).
    """

    dataset_model: type[T]

    async def load(self, storage: StorageProvider, dataset_id: str) -> T: ...

    async def store(self, storage: StorageProvider, dataset: T) -> dict: ...

    async def list_samples(
        self, storage: StorageProvider, dataset_id: str, offset: int, limit: int
    ) -> tuple[list, int]: ...

    async def add_samples(
        self, storage: StorageProvider, dataset_id: str, samples: list
    ) -> None: ...

    def view_for(self, view_type: str, sample: Any) -> BaseModel:
        """1:1 sample → view projection."""
        ...


class UpstreamAdapter(Protocol[T]):
    """Per-type contract for external data sources.

    ``T`` is the dataset-type-specific Pydantic model.
    """

    sample_model: T

    async def stream(
        self, source_uri: str, filters: dict | None = None
    ) -> AsyncIterator: ...
