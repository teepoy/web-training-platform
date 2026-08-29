from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any

import polars as pl
from sqlalchemy import create_engine, func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sc_upstream.upstream_db import SampleBatchStream

from .models import DefectORM, InspectionORM, PatchArchiveORM, ReviewImageORM


_SAMPLE_SCHEMA: Mapping[str, pl.DataType] = {
    "wafer_key": pl.Int64,
    "inspection_time": pl.Datetime("us", "UTC"),
    "defect_id": pl.Int64,
    "test_id": pl.Int32,
    "class_number": pl.Int32,
    "rough_bin": pl.Int32,
    "wafer_x": pl.Int32,
    "wafer_y": pl.Int32,
    "index_x": pl.Int32,
    "index_y": pl.Int32,
    "adder": pl.Int32,
    "cluster": pl.Int32,
    "images": pl.Int32,
    "size_x": pl.Int32,
    "size_y": pl.Int32,
    "size_d": pl.Int32,
    "area": pl.Int32,
    "final_bin": pl.Int32,
    "manual_bin": pl.Int32,
    "kill_ratio": pl.Float64,
    "lot_id": pl.String,
    "wafer_id": pl.String,
    "layer_id": pl.String,
    "inspect_equip_id": pl.String,
    "device": pl.String,
    "origin_x": pl.Int32,
    "origin_y": pl.Int32,
    "die_size_x": pl.Int32,
    "die_size_y": pl.Int32,
    "recipe_id": pl.String,
    "die_x": pl.Int32,
    "die_y": pl.Int32,
}

_SAMPLE_QUERY = """
SELECT d.wafer_key,
       d.inspection_time,
       d.defect_id,
       d.test_id,
       d.class_number,
       d.rough_bin,
       d.wafer_x,
       d.wafer_y,
       d.index_x,
       d.index_y,
       d.adder,
       d.cluster,
       d.images,
       d.size_x,
       d.size_y,
       d.size_d,
       d.area,
       d.final_bin,
       d.manual_bin,
       d.kill_ratio,
       i.lot_id,
       i.wafer_id,
       i.layer_id,
       i.inspect_equip_id,
       i.device,
       i.origin_x,
       i.origin_y,
       i.die_size_x,
       i.die_size_y,
       i.recipe_id,
       ((d.wafer_x - i.origin_x) % i.die_size_x) AS die_x,
       ((d.wafer_y - i.origin_y) % i.die_size_y) AS die_y
FROM simulator_defects d
JOIN simulator_inspections i
  ON d.wafer_key = i.wafer_key
 AND d.inspection_time = i.inspection_time
WHERE i.state = 'published'
  AND d.inspection_time = :inspection_time
  AND d.wafer_key = :wafer_key
ORDER BY d.defect_id
"""


def _sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + database_url.removeprefix(
            "postgresql+asyncpg://"
        )
    if database_url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + database_url.removeprefix("sqlite+aiosqlite://")
    raise ValueError("unsupported simulator database driver")


def _timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _sample_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    for row in rows:
        inspection_time = row["inspection_time"]
        if isinstance(inspection_time, str):
            inspection_time = datetime.fromisoformat(inspection_time)
        if inspection_time.tzinfo is None:
            inspection_time = inspection_time.replace(tzinfo=timezone.utc)
        row["inspection_time"] = inspection_time
    return pl.DataFrame(rows, schema=_SAMPLE_SCHEMA, strict=False)


class SimulatorUpstreamAdapter:
    """Expose published simulator records through the production SC transport."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        database_url: str,
    ) -> None:
        self._sessions = sessions
        self._sync_engine: Engine = create_engine(
            _sync_database_url(database_url), pool_pre_ping=True
        )

    def close(self) -> None:
        self._sync_engine.dispose()

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> dict[str, Any] | None:
        async with self._sessions() as session:
            inspection = await session.scalar(
                select(InspectionORM).where(
                    InspectionORM.inspection_time == inspection_time,
                    InspectionORM.wafer_key == wafer_key,
                    InspectionORM.state == "published",
                )
            )
            if inspection is None:
                return None
            defects, images = await self._counts(session, inspection)
            return self._inspection_dict(inspection, defects=defects, images=images)

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> pl.LazyFrame:
        defect_count = (
            select(func.count())
            .select_from(DefectORM)
            .where(
                DefectORM.wafer_key == InspectionORM.wafer_key,
                DefectORM.inspection_time == InspectionORM.inspection_time,
            )
            .correlate(InspectionORM)
            .scalar_subquery()
        )
        image_count = (
            select(func.count())
            .select_from(ReviewImageORM)
            .where(
                ReviewImageORM.wafer_key == InspectionORM.wafer_key,
                ReviewImageORM.inspection_time == InspectionORM.inspection_time,
            )
            .correlate(InspectionORM)
            .scalar_subquery()
        )
        statement = (
            select(
                InspectionORM,
                defect_count.label("defects"),
                image_count.label("images"),
            )
            .where(
                InspectionORM.state == "published",
                InspectionORM.inspection_time >= start_time,
                InspectionORM.inspection_time < end_time,
            )
            .order_by(
                InspectionORM.inspection_time.desc(), InspectionORM.wafer_key.desc()
            )
        )
        for column, raw_filter in (
            (InspectionORM.lot_id, lot_id),
            (InspectionORM.wafer_id, wafer_id),
            (InspectionORM.layer_id, layer_id),
            (InspectionORM.device, device),
        ):
            conditions = []
            for item in (part.strip() for part in raw_filter.split(",")):
                if not item:
                    continue
                conditions.append(
                    column.startswith(item[:-1])
                    if item.endswith("*")
                    else column == item
                )
            if conditions:
                statement = statement.where(or_(*conditions))

        async with self._sessions() as session:
            result = await session.execute(statement)
            rows = [
                self._inspection_dict(inspection, defects=defects, images=images)
                for inspection, defects, images in result.all()
            ]
        return pl.DataFrame(rows).lazy()

    async def list_samples(
        self, inspection_time: datetime, wafer_key: int
    ) -> pl.LazyFrame:
        frame = await asyncio.to_thread(
            self._read_sample_frame,
            inspection_time,
            wafer_key,
            offset=0,
            count=None,
        )
        return frame.lazy()

    async def get_sample_count(self, inspection_time: datetime, wafer_key: int) -> int:
        async with self._sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(DefectORM)
                .join(
                    InspectionORM,
                    (DefectORM.wafer_key == InspectionORM.wafer_key)
                    & (DefectORM.inspection_time == InspectionORM.inspection_time),
                )
                .where(
                    InspectionORM.state == "published",
                    DefectORM.inspection_time == inspection_time,
                    DefectORM.wafer_key == wafer_key,
                )
            )
            return int(count or 0)

    def open_list_samples_stream(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int = 65536,
        offset: int = 0,
        count: int | None = None,
    ) -> SampleBatchStream:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if count is not None and count < 0:
            raise ValueError("count must not be negative")

        batches = self._read_sample_batches(
            inspection_time,
            wafer_key,
            batch_size=batch_size,
            offset=offset,
            count=count,
        )
        return SampleBatchStream(
            schema=pl.DataFrame(schema=_SAMPLE_SCHEMA).to_arrow().schema,
            batches=batches,
        )

    async def list_review_images(
        self, inspection_time: datetime, wafer_key: int
    ) -> list[dict[str, Any]]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(ReviewImageORM)
                .join(
                    InspectionORM,
                    (ReviewImageORM.wafer_key == InspectionORM.wafer_key)
                    & (ReviewImageORM.inspection_time == InspectionORM.inspection_time),
                )
                .where(
                    InspectionORM.state == "published",
                    ReviewImageORM.inspection_time == inspection_time,
                    ReviewImageORM.wafer_key == wafer_key,
                )
                .order_by(ReviewImageORM.defect_id, ReviewImageORM.image_id)
            )
            return [
                {
                    "defect_id": image.defect_id,
                    "image_id": image.image_id,
                    "image_type": image.image_type,
                    "image_filespec": image.image_filespec,
                }
                for image in result
            ]

    async def get_inspection_patch_zips(
        self,
        inspection_time: datetime,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict[str, str]]:
        async with self._sessions() as session:
            result = await session.scalars(
                select(PatchArchiveORM)
                .join(
                    InspectionORM,
                    (PatchArchiveORM.wafer_key == InspectionORM.wafer_key)
                    & (
                        PatchArchiveORM.inspection_time == InspectionORM.inspection_time
                    ),
                )
                .where(
                    InspectionORM.state == "published",
                    InspectionORM.inspection_time == inspection_time,
                    InspectionORM.lot_id == lot_id,
                    InspectionORM.wafer_id == wafer_id,
                    InspectionORM.device == device,
                    InspectionORM.layer_id == layer_id,
                )
                .order_by(PatchArchiveORM.s3_key)
            )
            return [
                {"s3_bucket": archive.s3_bucket, "s3_key": archive.s3_key}
                for archive in result
            ]

    async def _counts(
        self, session: AsyncSession, inspection: InspectionORM
    ) -> tuple[int, int]:
        filters = (
            DefectORM.wafer_key == inspection.wafer_key,
            DefectORM.inspection_time == inspection.inspection_time,
        )
        defects = await session.scalar(
            select(func.count()).select_from(DefectORM).where(*filters)
        )
        images = await session.scalar(
            select(func.count())
            .select_from(ReviewImageORM)
            .where(
                ReviewImageORM.wafer_key == inspection.wafer_key,
                ReviewImageORM.inspection_time == inspection.inspection_time,
            )
        )
        return int(defects or 0), int(images or 0)

    @staticmethod
    def _inspection_dict(
        inspection: InspectionORM, *, defects: int, images: int
    ) -> dict[str, Any]:
        return {
            "inspection_time": _isoformat(inspection.inspection_time),
            "wafer_key": inspection.wafer_key,
            "lot_id": inspection.lot_id,
            "wafer_id": inspection.wafer_id,
            "device": inspection.device,
            "layer_id": inspection.layer_id,
            "center_x": inspection.center_x,
            "center_y": inspection.center_y,
            "origin_x": inspection.origin_x,
            "origin_y": inspection.origin_y,
            "die_size_x": inspection.die_size_x,
            "die_size_y": inspection.die_size_y,
            "eqp_id": inspection.inspect_equip_id,
            "inspect_equip_id": inspection.inspect_equip_id,
            "recipe_id": inspection.recipe_id,
            "defects": defects,
            "images": images,
            "origin_index_x": inspection.origin_index_x,
            "origin_index_y": inspection.origin_index_y,
            "latest_update": _timestamp(inspection.last_updated_at),
            "change_token": inspection.change_token or 0,
        }

    def _read_sample_frame(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        offset: int,
        count: int | None,
    ) -> pl.DataFrame:
        batches = list(
            self._read_sample_batches(
                inspection_time,
                wafer_key,
                batch_size=max(count or 65536, 1),
                offset=offset,
                count=count,
            )
        )
        return pl.concat(batches) if batches else pl.DataFrame(schema=_SAMPLE_SCHEMA)

    def _read_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int,
        offset: int,
        count: int | None,
    ) -> Iterator[pl.DataFrame]:
        query = _SAMPLE_QUERY
        if self._sync_engine.dialect.name == "sqlite":
            query = query.replace(
                "d.inspection_time = :inspection_time",
                "datetime(d.inspection_time) = datetime(:inspection_time)",
            )
        params: dict[str, Any] = {
            "inspection_time": (
                inspection_time.replace(tzinfo=None)
                if self._sync_engine.dialect.name == "sqlite"
                else inspection_time
            ),
            "wafer_key": wafer_key,
        }
        if count is not None:
            query += " LIMIT :count"
            params["count"] = count
        if offset:
            query += " OFFSET :offset"
            params["offset"] = offset

        with self._sync_engine.connect() as connection:
            result = connection.execute(text(query), params)
            for partition in result.mappings().partitions(batch_size):
                yield _sample_frame([dict(row) for row in partition])
