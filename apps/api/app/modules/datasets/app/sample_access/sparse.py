from __future__ import annotations

from typing import Protocol

from app.modules.storage.domain.sparse import SampleLocator


class SparseSampleAccess(Protocol):
    """Protocol for sparse sample resolution (Wave 2 implementation).

    Defines the contract for translating logical sample locators into
    concrete row data from file-backed shard storage, without relying on
    full SampleORM materialization.
    """

    async def list_sample_locators(
        self, dataset_id: str, offset: int, limit: int
    ) -> list[SampleLocator]: ...

    async def get_sample_row(
        self, dataset_id: str, locator: SampleLocator
    ) -> dict[str, object]: ...

    async def count_samples(self, dataset_id: str) -> int: ...
