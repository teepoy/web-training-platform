from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import polars as pl
import pyarrow.flight as flight  # pyright: ignore[reportPrivateImportUsage]
from grpc import aio as grpc_aio

from proto_stubs.sc.v1 import upstream_pb2 as pb
from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

if TYPE_CHECKING:
    from app.modules.sc.domain.models import ScInspectionRecord


class GrpcScUpstream:
    def __init__(
        self,
        grpc_addr: str = "sc-upstream:9091",
        flight_addr: str = "grpc://sc-upstream:9093",
    ) -> None:
        self._grpc_addr = grpc_addr
        self._flight_addr = flight_addr
        self._channel: grpc_aio.Channel | None = None
        self._stub: pb_grpc.ScUpstreamStub | None = None

    def _ensure_channel(self) -> pb_grpc.ScUpstreamStub:
        if self._stub is None:
            self._channel = grpc_aio.insecure_channel(self._grpc_addr)
            self._stub = pb_grpc.ScUpstreamStub(self._channel)
        return self._stub

    def _ensure_flight_client(self) -> flight.FlightClient:  # pyright: ignore[reportPrivateImportUsage]
        return flight.FlightClient(self._flight_addr)  # pyright: ignore[reportPrivateImportUsage]

    async def list_inspections(
        self, start_time: datetime, end_time: datetime
    ) -> pl.LazyFrame:
        stub = self._ensure_channel()
        req = pb.ListInspectionsRequest(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )
        resp = await stub.ListInspections(req)
        rows = [
            {
                "inspection_time": datetime.fromisoformat(i.inspection_time).replace(
                    tzinfo=timezone.utc
                ),
                "wafer_key": i.wafer_key,
                "lot_id": i.lot_id,
                "wafer_id": i.wafer_id,
                "device": i.device,
                "layer_id": i.layer_id,
                "inspect_equip_id": i.eqp_id,
                "recipe_id": i.recipe_id,
                "defects": i.defects,
                "images": i.images,
                "center_x": i.center_x,
                "center_y": i.center_y,
                "origin_x": i.origin_x,
                "origin_y": i.origin_y,
                "die_size_x": i.die_size_x,
                "die_size_y": i.die_size_y,
            }
            for i in resp.items
        ]
        return pl.DataFrame(rows).lazy()

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> ScInspectionRecord | None:
        from app.modules.sc.domain.models import ScInspectionRecord

        stub = self._ensure_channel()
        req = pb.GetInspectionRequest(
            inspection_time=inspection_time.isoformat(),
            wafer_key=wafer_key,
        )
        resp = await stub.GetInspection(req)
        if not resp.lot_id and not resp.wafer_id and not resp.device:
            return None
        return ScInspectionRecord(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            lot_id=resp.lot_id,
            wafer_id=resp.wafer_id,
            center_x=resp.center_x,
            center_y=resp.center_y,
            origin_x=resp.origin_x,
            origin_y=resp.origin_y,
            die_size_x=resp.die_size_x,
            die_size_y=resp.die_size_y,
            layer_id=resp.layer_id or None,
            eqp_id=resp.eqp_id or None,
            recipe_id=resp.recipe_id,
            defects=resp.defects,
            images=resp.images,
            device=resp.device,
            origin_index_x=resp.origin_index_x,
            origin_index_y=resp.origin_index_y,
            latest_update=resp.latest_update,
        )

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
        fc = self._ensure_flight_client()
        ticket = flight.Ticket(  # pyright: ignore[reportPrivateImportUsage]
            json.dumps(
                {
                    "type": "list_samples",
                    "inspection_time": inspection_time.isoformat(),
                    "wafer_key": wafer_key,
                }
            ).encode()
        )
        reader = fc.do_get(ticket)
        table = reader.read_all()
        df: pl.DataFrame = pl.from_arrow(table)  # type: ignore[assignment]

        if "die_x" not in df.columns:
            die_size_x: int = int(df["die_size_x"].max())  # type: ignore[index]
            die_size_y: int = int(df["die_size_y"].max())  # type: ignore[index]
            origin_x: int = int(df["origin_x"].max())  # type: ignore[index]
            origin_y: int = int(df["origin_y"].max())  # type: ignore[index]
            if die_size_x > 0:
                df = df.with_columns(
                    [
                        ((pl.col("wafer_x") - origin_x) % die_size_x).alias("die_x"),
                        ((pl.col("wafer_y") - origin_y) % die_size_y).alias("die_y"),
                    ]
                )

        lf = df.lazy()
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

        if offset:
            lf = lf.slice(offset, count or 0)
        elif count is not None:
            lf = lf.slice(0, count)
        return lf

    async def list_review_images(
        self, inspection_time: datetime, wafer_key: int
    ) -> pl.LazyFrame:
        stub = self._ensure_channel()
        req = pb.ListReviewImagesRequest(
            inspection_time=inspection_time.isoformat(),
            wafer_key=wafer_key,
        )
        resp = await stub.ListReviewImages(req)
        rows = [
            {
                "defect_id": img.defect_id,
                "image_id": img.image_id,
                "image_type": img.image_type,
                "image_filespec": img.image_filespec,
            }
            for img in resp.images
        ]
        return pl.DataFrame(rows).lazy()

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
