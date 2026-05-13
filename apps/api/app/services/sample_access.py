from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import Annotation, Sample


class SampleAccess(ABC):
    """Seam definition for sample-access backends.

    Declares the full set of sample-access method signatures that any
    storage-mode backend must implement.  This exists to support multiple
    storage modes without changing callers:

    * ``db_full`` — the current default: all samples live in the API DB
      and SqlRepository serves as the sole backend.  SqlRepository
      implicitly satisfies this seam without requiring inheritance.
    * ``file_shard_sparse`` — future mode: sample rows are read from
      file-backed parquet shards via a sparse adapter, while the API DB
      retains only metadata and foreign-key relationships.

    This class is a definition-only seam.  It does **not** contain any
    implementation, delegation, or dispatch logic — those belong in
    future work.
    """

    # ── create ────────────────────────────────────────────────────────

    @abstractmethod
    async def create_sample(self, sample: Sample) -> Sample: ...

    @abstractmethod
    async def create_samples(self, samples: list[Sample]) -> list[Sample]: ...

    # ── read (single) ─────────────────────────────────────────────────

    @abstractmethod
    async def get_sample(self, sample_id: str) -> Sample | None: ...

    # ── read (paginated / list) ───────────────────────────────────────

    @abstractmethod
    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[Sample], int]: ...

    @abstractmethod
    async def list_wafer_points(self, dataset_id: str) -> list[dict[str, object]]: ...

    @abstractmethod
    async def list_samples_with_labels(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        label_filter: str | None = None,
        order_by: str = "id",
        sample_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]: ...

    # ── annotation queries ────────────────────────────────────────────

    @abstractmethod
    async def get_annotation_stats(self, dataset_id: str) -> dict: ...

    @abstractmethod
    async def list_annotations_for_dataset(
        self, dataset_id: str
    ) -> list[Annotation]: ...

    @abstractmethod
    async def list_annotations_for_sample(self, sample_id: str) -> list[Annotation]: ...

    @abstractmethod
    async def recent_annotations(self, dataset_id: str, limit: int = 20) -> dict: ...

    # ── aggregation / analytics ───────────────────────────────────────

    @abstractmethod
    async def get_random_samples(
        self, dataset_id: str, limit: int = 100
    ) -> list[dict]: ...

    @abstractmethod
    async def metadata_histogram(self, dataset_id: str, key: str) -> dict: ...

    @abstractmethod
    async def similarity_search(
        self,
        embedding: list[float],
        dataset_id: str,
        k: int,
        exclude_id: str = "",
    ) -> list[dict]: ...

    @abstractmethod
    async def prediction_summary(self, dataset_id: str) -> dict: ...

    # ── write (mutate single) ─────────────────────────────────────────

    @abstractmethod
    async def update_sample_image_uris(
        self, sample_id: str, image_uris: list[str]
    ) -> Sample | None: ...

    @abstractmethod
    async def update_sample_ls_task_id(
        self, sample_id: str, ls_task_id: int
    ) -> None: ...
