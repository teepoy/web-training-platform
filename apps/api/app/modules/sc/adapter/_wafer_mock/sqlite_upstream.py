from __future__ import annotations

import asyncio
from datetime import datetime

import polars as pl
from sqlalchemy import create_engine
import async_lru

from app.modules.sc.domain.models import ScInspectionRecord

BATCH_SIZE = 50_000

_SCHEMA_OVERRIDES = {
    "wafer_key": pl.Int32,
    "defect_id": pl.Int32,
    "wafer_x": pl.Int32,
    "wafer_y": pl.Int32,
    "index_x": pl.Int32,
    "index_y": pl.Int32,
    "class_number": pl.Int32,
    "rough_bin": pl.Int32,
    "images": pl.Int32,
    "image_id": pl.Int32,
    "center_x": pl.Int32,
    "center_y": pl.Int32,
    "origin_x": pl.Int32,
    "origin_y": pl.Int32,
    "die_size_x": pl.Int32,
    "die_size_y": pl.Int32,
    "add": pl.Int32,
    "cluster": pl.Int32,
    "test_id": pl.Int32,
    "recipe_key": pl.Int32,
    "origin_index_x": pl.Int32,
    "origin_index_y": pl.Int32,
    "die_x": pl.Int32,
    "die_y": pl.Int32,
    "size_x": pl.Int32,
    "size_y": pl.Int32,
    "size_d": pl.Int32,
    "area": pl.Int32,
    "final_bin": pl.Int32,
    "manual_bin": pl.Int32,
    "kill_ratio": pl.Float64,
}


class SqliteScUpstream:
    """SC upstream reader backed by a SQLite wafer inspection database.

    Uses ``pl.read_database`` inside ``asyncio.to_thread`` so the
    synchronous polars read never blocks the async event loop.

    Each call to ``_read`` creates a fresh SQLAlchemy engine and
    disposes it — SQLite is single-file, no connection pool needed.
    """

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    def _read_sync(self, query: str, **kwargs) -> pl.LazyFrame:
        engine = create_engine(self._db_url)
        try:
            return pl.read_database(
                query=query,
                connection=engine,
                schema_overrides=_SCHEMA_OVERRIDES,
                **kwargs,  # type: ignore[arg-type]
            ).lazy()
        finally:
            engine.dispose()

    async def _read(self, query: str, **kwargs: object) -> pl.LazyFrame:
        return await asyncio.to_thread(self._read_sync, query, **kwargs)

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> ScInspectionRecord | None:
        insp_dt = (
            inspection_time.replace(tzinfo=None)
            if inspection_time.tzinfo is not None
            else inspection_time
        )
        insp_str = insp_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        query = f"""
        SELECT s.*, r.recipe_id, r.origin_index_x, r.origin_index_y
        FROM insp_wafer_summary s
        JOIN insp_recipe r ON s.recipe_key = r.recipe_key
        WHERE s.inspection_time = '{insp_str}' AND s.wafer_key = {wafer_key}
        """
        lf = await self._read(query)
        df = await asyncio.to_thread(lf.collect)
        if len(df) == 0:
            return None
        row = df.to_dicts()[0]
        return ScInspectionRecord(
            inspection_time=row["inspection_time"],
            wafer_key=row["wafer_key"],
            lot_id=row["lot_id"],
            wafer_id=row["wafer_id"],
            center_x=row["center_x"],
            center_y=row["center_y"],
            origin_x=row["origin_x"],
            origin_y=row["origin_y"],
            die_size_x=row["die_size_x"],
            die_size_y=row["die_size_y"],
            layer_id=row["layer_id"],
            eqp_id=row["inspect_equip_id"],
            recipe_id=row["recipe_id"],
            defects=row["defects"],
            images=row["images"],
            device=row["device"],
            origin_index_x=row["origin_index_x"],
            origin_index_y=row["origin_index_y"],
        )

    @async_lru.alru_cache(maxsize=3)
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
    ) -> pl.LazyFrame:
        insp_dt = (
            inspection_time.replace(tzinfo=None)
            if inspection_time.tzinfo is not None
            else inspection_time
        )
        insp_str = insp_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        query = f"""
        SELECT d.*,
               s.lot_id, s.wafer_id, s.layer_id, s.recipe_key, s.inspect_equip_id,
               s.device, s.center_x, s.center_y,
               s.origin_x, s.origin_y, s.die_size_x, s.die_size_y
        FROM inspect_defect d
        JOIN insp_wafer_summary s ON d.wafer_key = s.wafer_key AND d.inspection_time = s.inspection_time
        WHERE d.inspection_time = '{insp_str}' AND d.wafer_key = {wafer_key}
        ORDER BY d.defect_id
        """
        lf = await self._read(query)
        lf = lf.with_columns(
            [
                ((pl.col("wafer_x") - pl.col("origin_x")) % pl.col("die_size_x")).alias(
                    "die_x"
                ),
                ((pl.col("wafer_y") - pl.col("origin_y")) % pl.col("die_size_y")).alias(
                    "die_y"
                ),
            ]
        )
        lf = lf.with_columns(
            [
                (
                    pl.col("die_x")
                    + (
                        (pl.col("wafer_x") - pl.col("origin_x")) // pl.col("die_size_x")
                        + reticle_offset_x
                    )
                    % reticle_size_x
                    * pl.col("die_size_x")
                ).alias("reticle_x"),
                (
                    pl.col("die_y")
                    + (
                        (pl.col("wafer_y") - pl.col("origin_y")) // pl.col("die_size_y")
                        + reticle_offset_y
                    )
                    % reticle_size_y
                    * pl.col("die_size_y")
                ).alias("reticle_y"),
            ]
        )
        if count is not None:
            lf = lf.slice(offset, count)
        elif offset:
            lf = lf.slice(offset)
        return lf

    async def list_wafer_points(
        self,
        inspection_time: datetime,
        wafer_key: int,
        reticle_size_x: int = 1,
        reticle_size_y: int = 1,
        reticle_offset_x: int = 0,
        reticle_offset_y: int = 0,
    ) -> pl.LazyFrame:
        insp_str = inspection_time.strftime("%Y-%m-%d %H:%M:%S.%f")
        query = f"""
        SELECT d.defect_id, d.wafer_x, d.wafer_y, d.class_number, d.rough_bin, d.images,
               s.origin_x, s.origin_y, s.die_size_x, s.die_size_y
        FROM inspect_defect d
        JOIN insp_wafer_summary s ON d.wafer_key = s.wafer_key
            AND d.inspection_time = s.inspection_time
        WHERE d.inspection_time = '{insp_str}' AND d.wafer_key = {wafer_key}
        ORDER BY d.defect_id
        """
        lf = await self._read(query)
        lf = lf.with_columns(
            [
                ((pl.col("wafer_x") - pl.col("origin_x")) % pl.col("die_size_x")).alias(
                    "die_x"
                ),
                ((pl.col("wafer_y") - pl.col("origin_y")) % pl.col("die_size_y")).alias(
                    "die_y"
                ),
            ]
        )
        lf = lf.with_columns(
            [
                (
                    pl.col("die_x")
                    + (
                        (pl.col("wafer_x") - pl.col("origin_x")) // pl.col("die_size_x")
                        + reticle_offset_x
                    )
                    % reticle_size_x
                    * pl.col("die_size_x")
                ).alias("reticle_x"),
                (
                    pl.col("die_y")
                    + (
                        (pl.col("wafer_y") - pl.col("origin_y")) // pl.col("die_size_y")
                        + reticle_offset_y
                    )
                    % reticle_size_y
                    * pl.col("die_size_y")
                ).alias("reticle_y"),
            ]
        )
        lf = lf.select(
            [
                "defect_id",
                "wafer_x",
                "wafer_y",
                "die_x",
                "die_y",
                "reticle_x",
                "reticle_y",
                "class_number",
                "rough_bin",
                "images",
            ]
        )
        return lf

    async def list_review_images(
        self, inspection_time: datetime | str, wafer_key: int
    ) -> pl.LazyFrame:
        if isinstance(inspection_time, datetime):
            insp_dt = (
                inspection_time.replace(tzinfo=None)
                if inspection_time.tzinfo is not None
                else inspection_time
            )
            insp_str = insp_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            insp_str = inspection_time
        query = f"""
        SELECT d.defect_id, d.wafer_key, d.inspection_time,
               d.class_number, d.rough_bin, d.wafer_x, d.wafer_y,
               i.image_id, i.image_type, i.image_filespec
        FROM inspect_defect d
        JOIN inspect_image i ON d.wafer_key = i.wafer_key
          AND d.inspection_time = i.inspection_time
          AND d.defect_id = i.defect_id
        WHERE d.inspection_time = '{insp_str}' AND d.wafer_key = {wafer_key}
          AND d.images > 0
        ORDER BY d.defect_id, i.image_id
        """
        return await self._read(query)

    async def list_inspections(
        self, start_time: datetime, end_time: datetime
    ) -> pl.LazyFrame:
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        query = f"""
        SELECT s.*, r.recipe_id, r.origin_index_x, r.origin_index_y
        FROM insp_wafer_summary s
        JOIN insp_recipe r ON s.recipe_key = r.recipe_key
        WHERE s.inspection_time >= '{start_str}' AND s.inspection_time < '{end_str}'
        ORDER BY s.inspection_time DESC, s.wafer_key DESC
        """
        return await self._read(query)
