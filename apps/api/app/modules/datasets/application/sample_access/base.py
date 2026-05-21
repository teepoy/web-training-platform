from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import HTTPException

from app.domain.models import Annotation, Sample


class StorageModeNotSupported(HTTPException):
    """Raised when an operation is not supported by the current storage mode.

    Caught by a FastAPI exception handler → HTTP 409.
    """

    def __init__(self, operation: str, storage_mode: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"'{operation}' is not supported for {storage_mode} datasets",
        )


class SampleAccess(ABC):
    """Storage-mode-agnostic dataset sample operations.

    Implementations:
        DbFullSampleAccess  — wraps SqlRepository (SampleORM)
        SparseSampleAccess   — reads Parquet shards via PayloadStore

    Unsupported operations raise StorageModeNotSupported → HTTP 409.
    """

    # ── meta ───────────────────────────────────────────────────────────

    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Return feature flags for this storage mode."""

    # ── create ─────────────────────────────────────────────────────────

    @abstractmethod
    async def create_samples(self, samples: list[Sample]) -> list[Sample]:
        """Bulk create.  A single sample → wrap in list.

        Use cases: import, add single sample, VQA JSONL import.
        """

    # ── read ───────────────────────────────────────────────────────────

    @abstractmethod
    async def get_sample(self, sample_id: str) -> Sample | None:
        """Single sample lookup.

        Sparse mode: sample_id encodes (shard_index, row_index).
        """

    @abstractmethod
    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[Sample], int]:
        """Paginated listing.  Returns (samples, total_count).

        Use cases: browse, prediction batch, export, wafer filter, feature ops.
        Callers filter domain-specific metadata (e.g. wafer coords) from Sample.metadata.
        """

    @abstractmethod
    async def list_samples_with_labels(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        label_filter: str | None = None,
        order_by: str = "id",
        sample_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated listing enriched with latest annotation per sample.

        Returns (list[dict], total).  Each dict has sample fields plus
        optional ``latest_annotation`` key.

        Use cases: labeling queue, annotation review.
        """

    # ── annotations ────────────────────────────────────────────────────

    @abstractmethod
    async def list_annotations(
        self,
        *,
        dataset_id: str | None = None,
        sample_id: str | None = None,
        limit: int | None = None,
    ) -> list[Annotation]:
        """Scoped annotation listing.

        Use cases:
        * ``dataset_id=`` only      → dataset overview / sync to LS
        * ``sample_id=`` only       → per-sample annotation view
        * ``dataset_id= + limit=``  → recent annotation feed
        """

    @abstractmethod
    async def get_annotation_stats(self, dataset_id: str) -> dict:
        """Label distribution + coverage stats."""

    # ── aggregation ────────────────────────────────────────────────────

    @abstractmethod
    async def get_random_samples(
        self, dataset_id: str, limit: int = 100
    ) -> list[dict]: ...

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

    # ── update ─────────────────────────────────────────────────────────

    @abstractmethod
    async def update_sample(
        self,
        sample_id: str,
        *,
        image_uris: list[str] | None = None,
        ls_task_id: int | None = None,
    ) -> Sample | None:
        """Update sample fields.

        Use cases: upload images, sync Label Studio task ID.
        """
