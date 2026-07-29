from __future__ import annotations

from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.modules.storage.port.local import DatasetStorageFactoryPort


class SampleSimilarityService:
    def __init__(self, storage_factory: DatasetStorageFactoryPort) -> None:
        self._storage_factory = storage_factory

    async def _open_storage(
        self,
        dataset_id: str,
        org_id: str,
    ) -> DatasetStorageAgg:
        return await self._storage_factory.open(dataset_id, org_id)

    async def similarity_search(
        self,
        sample_id: str,
        dataset_id: str,
        org_id: str,
        k: int = 5,
    ) -> dict:
        storage = await self._open_storage(dataset_id, org_id)
        feature = await storage.get_sample_feature(sample_id)
        if feature is None or not feature.embedding:
            return {"sample_id": sample_id, "neighbors": []}

        neighbors = await storage.similarity_search(
            feature.embedding, k, exclude_id=sample_id
        )
        return {"sample_id": sample_id, "neighbors": neighbors}
