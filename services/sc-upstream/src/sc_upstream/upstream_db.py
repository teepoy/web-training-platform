from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import polars as pl

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .models import (
    Base,
    BaseZips,
    InspWaferSummaryORM,
    InspectImageORM,
    InspectionPatchImagesZipORM,
)


class UpstreamDB:
    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self._engine)

    async def _read(self, query: str) -> pl.LazyFrame:
        def _sync() -> pl.LazyFrame:
            conn = self._engine.connect()
            try:
                df = pl.read_database(query, connection=conn)
                return df.lazy()
            finally:
                conn.close()

        return await asyncio.to_thread(_sync)

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> dict[str, Any] | None:
        with Session(self._engine) as session:
            summary = session.get(InspWaferSummaryORM, (wafer_key, inspection_time))
            if summary is None:
                return None
            recipe_id = ""
            origin_index_x = 0
            origin_index_y = 0
            if summary.recipe and summary.recipe.recipe_id:
                recipe_id = summary.recipe.recipe_id
                origin_index_x = summary.recipe.origin_index_x
                origin_index_y = summary.recipe.origin_index_y
            return {
                "inspection_time": inspection_time.isoformat(),
                "wafer_key": wafer_key,
                "lot_id": summary.lot_id,
                "wafer_id": summary.wafer_id,
                "device": summary.device,
                "layer_id": summary.layer_id,
                "center_x": summary.center_x,
                "center_y": summary.center_y,
                "origin_x": summary.origin_x,
                "origin_y": summary.origin_y,
                "die_size_x": summary.die_size_x,
                "die_size_y": summary.die_size_y,
                "eqp_id": summary.inspect_equip_id,
                "recipe_id": recipe_id,
                "defects": summary.defects,
                "images": summary.images,
                "origin_index_x": origin_index_x,
                "origin_index_y": origin_index_y,
                "latest_update": int(summary.last_update.timestamp())
                if summary.last_update
                else 0,
            }

    async def list_inspections(
        self, start_time: datetime, end_time: datetime
    ) -> pl.LazyFrame:
        query = f"""
        SELECT s.wafer_key, s.inspection_time, s.lot_id, s.wafer_id, s.device,
               s.layer_id, s.inspect_equip_id, s.defects, s.images,
               s.center_x, s.center_y, s.origin_x, s.origin_y,
               s.die_size_x, s.die_size_y,
               r.recipe_id, r.origin_index_x, r.origin_index_y
        FROM insp_wafer_summary s
        JOIN insp_recipe r ON s.recipe_key = r.recipe_key
        WHERE s.inspection_time >= '{start_time}' AND s.inspection_time < '{end_time}'
        ORDER BY s.inspection_time DESC, s.wafer_key DESC
        """
        return await self._read(query)

    async def list_samples(
        self,
        inspection_time: datetime,
        wafer_key: int,
    ) -> pl.LazyFrame:
        insp_str = inspection_time.strftime("%Y-%m-%d %H:%M:%S.%f")
        query = f"""
        SELECT d.*,
               s.lot_id, s.wafer_id, s.layer_id, s.inspect_equip_id,
               s.device, s.origin_x, s.origin_y,
               s.die_size_x, s.die_size_y,
               r.recipe_id
        FROM inspect_defect d
        JOIN insp_wafer_summary s ON d.wafer_key = s.wafer_key
            AND d.inspection_time = s.inspection_time
        JOIN insp_recipe r ON s.recipe_key = r.recipe_key
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
        return lf

    def get_review_image_filespec(
        self, inspection_time: datetime, wafer_key: int, defect_id: int, image_id: int
    ) -> str | None:
        with Session(self._engine) as session:
            image = session.get(
                InspectImageORM, (wafer_key, inspection_time, defect_id, image_id)
            )
            if image is not None:
                return image.image_filespec
            return None

    def list_review_images(
        self, inspection_time: datetime, wafer_key: int, defect_id: int | None = None
    ) -> list[dict[str, Any]]:
        with Session(self._engine) as session:
            q = session.query(InspectImageORM).filter(
                InspectImageORM.inspection_time == inspection_time,
                InspectImageORM.wafer_key == wafer_key,
            )
            if defect_id is not None:
                q = q.filter(InspectImageORM.defect_id == defect_id)
            images = q.order_by(
                InspectImageORM.defect_id.asc(), InspectImageORM.image_id.asc()
            ).all()
            return [
                {
                    "defect_id": img.defect_id,
                    "image_id": img.image_id,
                    "image_type": img.image_type,
                    "image_filespec": img.image_filespec,
                }
                for img in images
            ]


class InspectionZipsDB:
    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(db_url, echo=False)
        BaseZips.metadata.create_all(self._engine)

    def get_inspection_patch_zips(
        self,
        inspection_time: datetime,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict[str, str]]:
        with Session(self._engine) as session:
            zips = (
                session.query(InspectionPatchImagesZipORM)
                .filter(
                    InspectionPatchImagesZipORM.inspection_time == inspection_time,
                    InspectionPatchImagesZipORM.lot_id == lot_id,
                    InspectionPatchImagesZipORM.wafer_id == wafer_id,
                    InspectionPatchImagesZipORM.device == device,
                    InspectionPatchImagesZipORM.layer_id == layer_id,
                )
                .order_by(InspectionPatchImagesZipORM.s3_key)
                .all()
            )
            return [{"s3_bucket": z.s3_bucket, "s3_key": z.s3_key} for z in zips]
