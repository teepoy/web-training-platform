from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING

import pyarrow as pa
import polars as pl
import pyarrow.flight as flight  # pyright: ignore[reportPrivateImportUsage]
from grpc import aio as grpc_aio

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScSampleProgressCallback
from proto_stubs.sc.v1 import upstream_pb2 as pb
from proto_stubs.sc.v1 import upstream_pb2_grpc as pb_grpc

if TYPE_CHECKING:
    from app.modules.sc.domain.models import ScInspectionRecord


def _parse_upstream_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return _coerce_naive_to_upstream_tz(dt)


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

    def _read_list_samples_table(
        self,
        ticket: flight.Ticket,  # pyright: ignore[reportPrivateImportUsage]
        on_progress: ScSampleProgressCallback | None,
    ) -> pa.Table:
        fc = self._ensure_flight_client()
        reader = fc.do_get(ticket)
        batches: list[pa.RecordBatch] = []
        loaded = 0
        while True:
            try:
                chunk = reader.read_chunk()
            except StopIteration:
                break
            data = chunk.data
            if data is None or data.num_rows == 0:
                continue
            if isinstance(data, pa.Table):
                batches.extend(data.to_batches())
            else:
                batches.append(data)
            loaded += data.num_rows
            if on_progress is not None:
                on_progress(loaded)
        if not batches:
            return pa.table({})
        return pa.Table.from_batches(batches)

    @staticmethod
    def _read_flight_chunk(
        reader: flight.FlightStreamReader,  # pyright: ignore[reportPrivateImportUsage]
    ) -> pa.Table | pa.RecordBatch | None:
        try:
            return reader.read_chunk().data
        except StopIteration:
            return None

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str | None = None,
        wafer_id: str | None = None,
        layer_id: str | None = None,
        device: str | None = None,
    ) -> pl.LazyFrame:
        stub = self._ensure_channel()
        req = pb.ListInspectionsRequest(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            lot_id=lot_id or "",
            wafer_id=wafer_id or "",
            layer_id=layer_id or "",
            device=device or "",
        )
        resp = await stub.ListInspections(req)
        rows = [
            {
                "inspection_time": _parse_upstream_datetime(i.inspection_time),
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

    async def get_sample_count(self, inspection_time: datetime, wafer_key: int) -> int:
        inspection = await self.get_inspection(inspection_time, wafer_key)
        return max(int(inspection.defects), 0) if inspection is not None else 0

    async def stream_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        offset: int = 0,
        count: int | None = None,
        batch_rows: int,
        projection: Sequence[str] | None = None,
        on_progress: ScSampleProgressCallback | None = None,
    ) -> AsyncIterator[pa.RecordBatch]:
        if offset < 0:
            raise ValueError("offset must not be negative")
        if count is not None and count < 0:
            raise ValueError("count must not be negative")
        if batch_rows <= 0:
            raise ValueError("batch_rows must be greater than zero")

        ticket = flight.Ticket(  # pyright: ignore[reportPrivateImportUsage]
            json.dumps(
                {
                    "type": "list_samples",
                    "inspection_time": inspection_time.isoformat(),
                    "wafer_key": wafer_key,
                    "offset": offset,
                    "count": count,
                    "batch_rows": batch_rows,
                    "projection": list(projection) if projection is not None else None,
                }
            ).encode()
        )
        client = self._ensure_flight_client()
        reader = await asyncio.to_thread(client.do_get, ticket)
        loaded = 0
        try:
            while True:
                data = await asyncio.to_thread(self._read_flight_chunk, reader)
                if data is None:
                    break
                batches = data.to_batches() if isinstance(data, pa.Table) else [data]
                for batch in batches:
                    if batch.num_rows == 0:
                        continue
                    loaded += batch.num_rows
                    if on_progress is not None:
                        on_progress(loaded)
                    yield batch
        finally:
            with suppress(Exception):
                await asyncio.to_thread(reader.cancel)

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
    ) -> pl.LazyFrame:
        batches = [
            batch
            async for batch in self.stream_sample_batches(
                inspection_time,
                wafer_key,
                offset=offset,
                count=count,
                batch_rows=65_536,
                on_progress=on_progress,
            )
        ]
        table = pa.Table.from_batches(batches) if batches else pa.table({})
        df: pl.DataFrame = pl.from_arrow(table)  # type: ignore[assignment]

        if df.height == 0 and not df.columns:
            df = pl.DataFrame(
                {
                    "defect_id": pl.Series([], dtype=pl.Int64),
                    "wafer_x": pl.Series([], dtype=pl.Int64),
                    "wafer_y": pl.Series([], dtype=pl.Int64),
                    "origin_x": pl.Series([], dtype=pl.Int64),
                    "origin_y": pl.Series([], dtype=pl.Int64),
                    "die_size_x": pl.Series([], dtype=pl.Int64),
                    "die_size_y": pl.Series([], dtype=pl.Int64),
                }
            )
        elif "defect_id" not in df.columns:
            df = (
                df.with_row_index("_row_index")
                .with_columns(pl.col("_row_index").cast(pl.Int64).alias("defect_id"))
                .drop("_row_index")
            )

        geometry_exprs: list[pl.Expr] = []
        for column, default in (
            ("wafer_x", 0),
            ("wafer_y", 0),
            ("origin_x", 0),
            ("origin_y", 0),
            ("die_size_x", 1),
            ("die_size_y", 1),
        ):
            if column not in df.columns:
                geometry_exprs.append(pl.lit(default).cast(pl.Int64).alias(column))
        if geometry_exprs:
            df = df.with_columns(geometry_exprs)
        df = df.with_columns(
            [
                pl.col("die_size_x").fill_null(1).clip(lower_bound=1),
                pl.col("die_size_y").fill_null(1).clip(lower_bound=1),
            ]
        )

        if "die_x" not in df.columns or "die_y" not in df.columns:
            df = df.with_columns(
                [
                    (
                        (pl.col("wafer_x") - pl.col("origin_x")) % pl.col("die_size_x")
                    ).alias("die_x"),
                    (
                        (pl.col("wafer_y") - pl.col("origin_y")) % pl.col("die_size_y")
                    ).alias("die_y"),
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
        return pl.DataFrame(
            rows,
            schema={
                "defect_id": pl.Int64,
                "image_id": pl.Int64,
                "image_type": pl.Utf8,
                "image_filespec": pl.Utf8,
            },
        ).lazy()

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
