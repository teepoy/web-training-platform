from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

import polars as pl
import pyarrow as pa


@dataclass(frozen=True)
class SampleBatchStream:
    schema: pa.Schema
    batches: Iterator[pl.DataFrame]


class InspectionDiscoveryOrder(StrEnum):
    PRIMARY_KEY = "primary_key"
    PUBLICATION = "publication"


@dataclass(frozen=True, slots=True)
class InspectionPrimaryKeyCursor:
    inspection_time: datetime
    wafer_key: int


@dataclass(frozen=True, slots=True)
class InspectionPublicationCursor:
    published_at: datetime
    inspection_time: datetime
    wafer_key: int


@dataclass(frozen=True, slots=True)
class InspectionDiscoveryQuery:
    order: InspectionDiscoveryOrder
    page_size: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    published_from: datetime | None = None
    published_until: datetime | None = None
    after_primary_key: InspectionPrimaryKeyCursor | None = None
    after_publication: InspectionPublicationCursor | None = None


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

    async def list_discovery_inspections(
        self, query: InspectionDiscoveryQuery
    ) -> pl.DataFrame: ...

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
