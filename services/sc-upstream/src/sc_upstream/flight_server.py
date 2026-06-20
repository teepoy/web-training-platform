from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Iterator

import pyarrow.flight as flight
import pyarrow as pa
import polars as pl

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
        req: dict = json.loads(ticket.ticket.decode())
        if req["type"] != "list_samples":
            raise ValueError(f"unknown ticket type: {req['type']}")

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
            batch_size=int(os.environ.get("SC_FLIGHT_BATCH_SIZE", "8192")),
            delay_seconds=float(os.environ.get("SC_UPSTREAM_DB_DELAY_SECONDS", "0")),
        )
        try:
            first_df = next(batch_iter)
        except StopIteration:
            lock_ctx.__exit__(None, None, None)
            return flight.RecordBatchStream(pa.table({}))

        def _stream_batches() -> Iterator[pa.Table]:
            frames: list[pl.DataFrame] = []
            try:
                frames.append(first_df)
                yield first_df.to_arrow()
                for df in batch_iter:
                    frames.append(df)
                    yield df.to_arrow()
                self._cache.sync_set_list_samples_from_frames(
                    req["inspection_time"], wafer_key, frames
                )
            finally:
                lock_ctx.__exit__(None, None, None)

        return flight.GeneratorStream(first_df.to_arrow().schema, _stream_batches())
