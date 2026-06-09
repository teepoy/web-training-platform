from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import Annotation, Dataset, Sample


class DatasetReader(Protocol):
    async def get_dataset(
        self,
        dataset_id: str,
        org_id: str | None = None,
    ) -> Dataset | None: ...

    async def list_samples(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Sample], int]: ...

    async def create_annotation(self, annotation: Annotation) -> Annotation: ...
