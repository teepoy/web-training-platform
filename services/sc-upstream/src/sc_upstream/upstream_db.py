from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import polars as pl
import pyarrow as pa


@dataclass(frozen=True)
class SampleBatchStream:
    schema: pa.Schema
    batches: Iterator[pl.DataFrame]


class UpstreamDB(Protocol):
    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> dict[str, Any] | None: ...

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> pl.LazyFrame: ...

    async def list_samples(
        self,
        inspection_time: datetime,
        wafer_key: int,
    ) -> pl.LazyFrame: ...

    async def get_sample_count(
        self, inspection_time: datetime, wafer_key: int
    ) -> int: ...

    def open_list_samples_stream(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int = 65536,
        offset: int = 0,
        count: int | None = None,
    ) -> SampleBatchStream: ...

    async def list_review_images(
        self, inspection_time: datetime, wafer_key: int
    ) -> list[dict[str, Any]]: ...


class InspectionZipsDB(Protocol):
    async def get_inspection_patch_zips(
        self,
        inspection_time: datetime,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict[str, str]]: ...
