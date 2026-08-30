from __future__ import annotations

import json
import os
from datetime import datetime
from contextlib import suppress
from typing import Any, Iterator

import polars as pl
import pyarrow as pa
import pyarrow.flight as flight

from .cache import QueryCache
from .upstream_db import UpstreamDB


class UpstreamFlightServer(flight.FlightServerBase):
    def __init__(
        self,
        db: UpstreamDB,
        cache: QueryCache | None,
        location: str = "grpc://0.0.0.0:9093",
    ) -> None:
        super().__init__(location)
        self._db = db
        self._cache = cache

    def do_get(
        self, context: flight.ServerCallContext, ticket: flight.Ticket
    ) -> flight.FlightDataStream:
        req = _parse_ticket(ticket)

        inspection_time = datetime.fromisoformat(req["inspection_time"])
        wafer_key: int = req["wafer_key"]
        if req["type"] == "list_membership_samples":
            return self._membership_stream(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                defect_ids=req["defect_ids"],
                projection=req["projection"],
                batch_rows=req["batch_rows"],
            )
        offset: int = req["offset"]
        count: int | None = req["count"]
        batch_rows: int = req["batch_rows"]
        projection: list[str] | None = req["projection"]

        if self._cache is None:
            return self._uncached_stream(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                offset=offset,
                count=count,
                batch_rows=batch_rows,
                projection=projection,
            )

        cached = self._cache.sync_get_list_samples(req["inspection_time"], wafer_key)
        if cached is not None:
            bounded = (
                cached.slice(offset, count)
                if count is not None
                else cached.slice(offset)
            )
            if projection is not None:
                bounded = bounded.select(projection)
            return _lazyframe_stream(bounded, batch_rows=batch_rows)

        full_request = offset == 0 and count is None and projection is None
        if not full_request:
            return self._uncached_stream(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                offset=offset,
                count=count,
                batch_rows=batch_rows,
                projection=projection,
            )

        lock_ctx = self._cache.sync_fill_lock(
            "samples", req["inspection_time"], str(wafer_key)
        )
        acquired = lock_ctx.__enter__()
        if not acquired:
            try:
                waited = self._cache.sync_wait_for_fill(
                    lambda: self._cache.sync_get_list_samples(
                        req["inspection_time"], wafer_key
                    )
                )
                if waited is not None:
                    return flight.RecordBatchStream(waited.collect().to_arrow())
            finally:
                lock_ctx.__exit__(None, None, None)
            lock_ctx = self._cache.sync_fill_lock(
                "samples", req["inspection_time"], str(wafer_key)
            )
            acquired = lock_ctx.__enter__()

        cached = self._cache.sync_get_list_samples(req["inspection_time"], wafer_key)
        if cached is not None:
            lock_ctx.__exit__(None, None, None)
            return flight.RecordBatchStream(cached.collect().to_arrow())

        sample_stream = self._db.open_list_samples_stream(
            inspection_time,
            wafer_key,
            batch_size=batch_rows,
        )

        def _stream_batches() -> Iterator[pa.Table]:
            writer = self._cache.sync_start_list_samples_writer(
                req["inspection_time"],
                wafer_key,
                sample_stream.schema,
            )
            try:
                for df in sample_stream.batches:
                    writer.write_frame(df)
                    yield df.to_arrow()
                writer.finish()
            except Exception:
                writer.abort()
                raise
            finally:
                lock_ctx.__exit__(None, None, None)

        return flight.GeneratorStream(sample_stream.schema, _stream_batches())

    def _uncached_stream(
        self,
        *,
        inspection_time: datetime,
        wafer_key: int,
        offset: int,
        count: int | None,
        batch_rows: int,
        projection: list[str] | None,
    ) -> flight.FlightDataStream:
        sample_stream = self._db.open_list_samples_stream(
            inspection_time,
            wafer_key,
            batch_size=batch_rows,
            offset=offset,
            count=count,
        )
        schema = _project_schema(sample_stream.schema, projection)

        def _stream_batches() -> Iterator[pa.Table]:
            try:
                for frame in sample_stream.batches:
                    if projection is not None:
                        frame = frame.select(projection)
                    yield frame.to_arrow()
            finally:
                with suppress(Exception):
                    sample_stream.batches.close()  # type: ignore[attr-defined]

        return flight.GeneratorStream(schema, _stream_batches())

    def _membership_stream(
        self,
        *,
        inspection_time: datetime,
        wafer_key: int,
        defect_ids: list[int],
        projection: list[str] | None,
        batch_rows: int,
    ) -> flight.FlightDataStream:
        sample_stream = self._db.open_membership_samples_stream(
            inspection_time,
            wafer_key,
            defect_ids=defect_ids,
            projection=projection,
            batch_size=batch_rows,
        )

        def _stream_batches() -> Iterator[pa.Table]:
            try:
                for frame in sample_stream.batches:
                    yield frame.to_arrow()
            finally:
                with suppress(Exception):
                    sample_stream.batches.close()  # type: ignore[attr-defined]

        return flight.GeneratorStream(sample_stream.schema, _stream_batches())


def _lazyframe_stream(frame: Any, *, batch_rows: int) -> flight.FlightDataStream:
    schema = pl.DataFrame(schema=frame.collect_schema()).to_arrow().schema
    batches = frame.collect_batches(chunk_size=batch_rows, maintain_order=True)

    def _stream() -> Iterator[pa.Table]:
        for batch in batches:
            yield batch.to_arrow()

    return flight.GeneratorStream(schema, _stream())


def _project_schema(schema: pa.Schema, projection: list[str] | None) -> pa.Schema:
    if projection is None:
        return schema
    return pa.schema(
        [schema.field(column) for column in projection],
        metadata=schema.metadata,
    )


def _parse_ticket(ticket: flight.Ticket) -> dict[str, Any]:
    try:
        req = json.loads(ticket.ticket.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Flight ticket JSON") from exc
    if not isinstance(req, dict):
        raise ValueError("Flight ticket must decode to a JSON object")
    ticket_type = req.get("type")
    if ticket_type not in {"list_samples", "list_membership_samples"}:
        raise ValueError(f"unknown ticket type: {req.get('type')}")
    inspection_time = req.get("inspection_time")
    if not isinstance(inspection_time, str) or not inspection_time:
        raise ValueError("list_samples Flight ticket requires inspection_time")
    try:
        datetime.fromisoformat(inspection_time)
    except ValueError as exc:
        raise ValueError("invalid inspection_time format") from exc
    wafer_key = req.get("wafer_key")
    if not isinstance(wafer_key, int):
        raise ValueError("list_samples Flight ticket requires integer wafer_key")
    batch_rows = req.get("batch_rows")
    if batch_rows is None:
        batch_rows = int(os.environ["SC_FLIGHT_BATCH_SIZE"])
    if not isinstance(batch_rows, int) or batch_rows <= 0:
        raise ValueError("list_samples Flight ticket requires positive batch_rows")
    projection = req.get("projection")
    if projection is not None:
        if not isinstance(projection, list) or not all(
            isinstance(column, str) and column.isidentifier() for column in projection
        ):
            raise ValueError(
                "list_samples Flight ticket projection must be identifiers"
            )
        if len(set(projection)) != len(projection):
            raise ValueError(
                "list_samples Flight ticket projection contains duplicates"
            )
    req["batch_rows"] = batch_rows
    req["projection"] = projection
    if ticket_type == "list_membership_samples":
        defect_ids = req.get("defect_ids")
        if (
            not isinstance(defect_ids, list)
            or not defect_ids
            or not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in defect_ids
            )
        ):
            raise ValueError(
                "list_membership_samples Flight ticket requires integer defect_ids"
            )
        if len(defect_ids) > batch_rows:
            raise ValueError(
                "list_membership_samples defect_ids must fit within batch_rows"
            )
        if len(set(defect_ids)) != len(defect_ids):
            raise ValueError(
                "list_membership_samples Flight ticket contains duplicate defect_ids"
            )
        req["defect_ids"] = defect_ids
        return req
    offset = req.get("offset", 0)
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("list_samples Flight ticket requires non-negative offset")
    count = req.get("count")
    if count is not None and (not isinstance(count, int) or count < 0):
        raise ValueError(
            "list_samples Flight ticket count must be null or non-negative"
        )
    req["offset"] = offset
    req["count"] = count
    return req
