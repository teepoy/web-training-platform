from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import polars as pl
import pyarrow as pa

from app.modules.sc.domain.models import ScInspectionRecord

ScSampleProgressCallback = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class ScInspectionKey:
    inspection_time: datetime
    wafer_key: int


@dataclass(frozen=True, slots=True)
class ScInspectionPublicationCursor:
    published_at: datetime
    inspection_time: datetime
    wafer_key: int


class ScUpstreamReader(Protocol):
    """Protocol for reading SC upstream (wafer inspection) data.

    Implementations read from wafer inspection upstreams and return
    ``pl.LazyFrame`` for bulk list methods and domain model types
    from ``app.modules.sc.domain.models`` for single-record lookups.
    """

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str | None = None,
        wafer_id: str | None = None,
        layer_id: str | None = None,
        device: str | None = None,
    ) -> pl.LazyFrame: ...

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> ScInspectionRecord | None: ...

    async def get_sample_count(
        self, inspection_time: datetime, wafer_key: int
    ) -> int: ...

    def stream_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        offset: int = 0,
        count: int | None = None,
        batch_rows: int,
        projection: Sequence[str] | None = None,
        on_progress: ScSampleProgressCallback | None = None,
    ) -> AsyncIterator[pa.RecordBatch]: ...

    async def list_samples(
        self,
        inspection_time: datetime,
        wafer_key: int,
        offset: int = 0,
        count: int | None = None,
        reticle_size_x: int = 1,
        reticle_size_y: int = 1,
        reticle_offset_x: int = 0,
        reticle_offset_y: int = 0,
        on_progress: ScSampleProgressCallback | None = None,
    ) -> pl.LazyFrame: ...

    async def list_review_images(
        self,
        inspection_time: datetime,
        wafer_key: int,
    ) -> pl.LazyFrame: ...


class ScDiscoveryUpstreamReader(ScUpstreamReader, Protocol):
    async def list_inspection_page(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        after: ScInspectionKey | None,
        page_size: int,
    ) -> pl.DataFrame: ...

    async def list_published_inspection_page(
        self,
        *,
        published_from: datetime,
        published_until: datetime,
        after: ScInspectionPublicationCursor | None,
        page_size: int,
    ) -> pl.DataFrame: ...
