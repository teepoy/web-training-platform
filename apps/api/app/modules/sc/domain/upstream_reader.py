from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import polars as pl

from app.modules.sc.domain.models import ScInspectionRecord


class ScUpstreamReader(Protocol):
    """Protocol for reading SC upstream (wafer inspection) data.

    Implementations read from wafer inspection upstreams and return
    ``pl.LazyFrame`` for bulk list methods and domain model types
    from ``app.modules.sc.domain.models`` for single-record lookups.
    """

    async def list_inspections(
        self, start_time: datetime, end_time: datetime
    ) -> pl.LazyFrame: ...

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> ScInspectionRecord | None: ...

    async def list_samples(
        self,
        inspection_time: datetime,
        wafer_key: int,
        offset: int = 0,
        count: int = 50,
        reticle_size_x: int = 1,
        reticle_size_y: int = 1,
        reticle_offset_x: int = 0,
        reticle_offset_y: int = 0,
    ) -> pl.LazyFrame: ...

    async def list_review_images(
        self,
        inspection_time: datetime,
        wafer_key: int,
    ) -> pl.LazyFrame: ...

    async def list_wafer_points(
        self,
        inspection_time: datetime,
        wafer_key: int,
        reticle_size_x: int = 1,
        reticle_size_y: int = 1,
        reticle_offset_x: int = 0,
        reticle_offset_y: int = 0,
    ) -> pl.LazyFrame: ...

    def stream(
        self,
        source_inspection_time: str,
        source_wafer_key: int,
        offset: int = 0,
    ) -> AsyncIterator[pl.DataFrame]:
        """Return an async iterator over DataFrame chunks.

        Implementations must return a synchronous callable that produces
        an ``AsyncIterator`` (e.g. a generator-based async iterator).
        ``offset`` skips the first N upstream rows in deterministic stream
        order.
        """
        ...
