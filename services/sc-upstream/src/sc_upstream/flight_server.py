from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pyarrow.flight as flight
from polars import LazyFrame

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

        cached = self._cache.get_list_samples(req["inspection_time"], wafer_key)
        if cached is not None:
            table = cached.collect().to_arrow()
            return flight.RecordBatchStream(table)

        lf: LazyFrame = asyncio.run(self._db.list_samples(inspection_time, wafer_key))
        self._cache.set_list_samples(req["inspection_time"], wafer_key, lf)
        table = lf.collect().to_arrow()
        return flight.RecordBatchStream(table)
