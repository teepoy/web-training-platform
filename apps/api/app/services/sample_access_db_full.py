from __future__ import annotations

from app.domain.models import Annotation, Sample
from app.repositories.sql_repository import SqlRepository
from app.services.sample_access import SampleAccess


class DbFullSampleAccess(SampleAccess):
    """Full-featured sample access via SqlRepository (SampleORM)."""

    def __init__(self, repo: SqlRepository) -> None:
        self._repo = repo

    # ── meta ───────────────────────────────────────────────────────

    def capabilities(self) -> dict[str, bool]:
        return {
            "can_create_samples": True,
            "can_list_samples": True,
            "can_annotate": True,
            "can_train": True,
            "can_predict": True,
            "can_export": True,
            "can_similarity_search": True,
            "can_random_sampling": True,
        }

    # ── create ─────────────────────────────────────────────────────

    async def create_samples(self, samples: list[Sample]) -> list[Sample]:
        return await self._repo.create_samples(samples)

    # ── read ───────────────────────────────────────────────────────

    async def get_sample(self, sample_id: str) -> Sample | None:
        return await self._repo.get_sample(sample_id)

    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[Sample], int]:
        return await self._repo.list_samples(dataset_id, offset=offset, limit=limit)

    async def list_samples_with_labels(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        label_filter: str | None = None,
        order_by: str = "id",
        sample_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        return await self._repo.list_samples_with_labels(
            dataset_id=dataset_id,
            offset=offset,
            limit=limit,
            label_filter=label_filter,
            order_by=order_by,
            sample_ids=sample_ids,
        )

    # ── annotations ────────────────────────────────────────────────

    async def list_annotations(
        self,
        *,
        dataset_id: str | None = None,
        sample_id: str | None = None,
        limit: int | None = None,
    ) -> list[Annotation]:
        if sample_id is not None:
            return await self._repo.list_annotations_for_sample(sample_id)
        if dataset_id is not None and limit is not None:
            raw = await self._repo.recent_annotations(dataset_id, limit=limit)
            return [
                Annotation(
                    id=e["id"],
                    sample_id=e["sample_id"],
                    label=e["label"],
                    created_by=e["created_by"],
                )
                for e in raw["entries"]
            ]
        if dataset_id is not None:
            return await self._repo.list_annotations_for_dataset(dataset_id)
        return []

    async def get_annotation_stats(self, dataset_id: str) -> dict:
        return await self._repo.get_annotation_stats(dataset_id)

    # ── aggregation ────────────────────────────────────────────────

    async def get_random_samples(self, dataset_id: str, limit: int = 100) -> list[dict]:
        return await self._repo.get_random_samples(dataset_id, limit=limit)

    async def similarity_search(
        self,
        embedding: list[float],
        dataset_id: str,
        k: int,
        exclude_id: str = "",
    ) -> list[dict]:
        return await self._repo.similarity_search(
            embedding, dataset_id, k, exclude_id=exclude_id
        )

    async def prediction_summary(self, dataset_id: str) -> dict:
        return await self._repo.prediction_summary(dataset_id)

    # ── update ─────────────────────────────────────────────────────

    async def update_sample(
        self,
        sample_id: str,
        *,
        image_uris: list[str] | None = None,
        ls_task_id: int | None = None,
    ) -> Sample | None:
        if image_uris is not None:
            return await self._repo.update_sample_image_uris(sample_id, image_uris)
        if ls_task_id is not None:
            await self._repo.update_sample_ls_task_id(sample_id, ls_task_id)
            return await self._repo.get_sample(sample_id)
        return None
