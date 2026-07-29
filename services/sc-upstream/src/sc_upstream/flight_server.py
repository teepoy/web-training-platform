from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Iterator

import pyarrow.flight as flight
import pyarrow as pa

from .cache import QueryCache
from .upstream_db import UpstreamDB


class UpstreamFlightServer(flight.FlightServerBase):
    def __init__(
        self, db: UpstreamDB, cache: QueryCache, location: str = "grpc://0.0.0.0:9093"
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

        cached = self._cache.sync_get_list_samples(req["inspection_time"], wafer_key)
        if cached is not None:
            return flight.RecordBatchStream(cached.collect().to_arrow())

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

        batch_iter = self._db.iter_list_samples_batches(
            inspection_time,
            wafer_key,
            batch_size=int(os.environ.get("SC_FLIGHT_BATCH_SIZE", "65536")),
        )
        try:
            first_df = next(batch_iter)
        except StopIteration:
            lock_ctx.__exit__(None, None, None)
            return flight.RecordBatchStream(pa.table({}))

        def _stream_batches() -> Iterator[pa.Table]:
            writer = self._cache.sync_start_list_samples_writer(
                req["inspection_time"],
                wafer_key,
                first_df.to_arrow().schema,
            )
            try:
                writer.write_frame(first_df)
                yield first_df.to_arrow()
                for df in batch_iter:
                    writer.write_frame(df)
                    yield df.to_arrow()
                writer.finish()
            except Exception:
                writer.abort()
                raise
            finally:
                lock_ctx.__exit__(None, None, None)

        return flight.GeneratorStream(first_df.to_arrow().schema, _stream_batches())


def _parse_ticket(ticket: flight.Ticket) -> dict[str, Any]:
    try:
        req = json.loads(ticket.ticket.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Flight ticket JSON") from exc
    if not isinstance(req, dict):
        raise ValueError("Flight ticket must decode to a JSON object")
    if req.get("type") != "list_samples":
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
    return req
