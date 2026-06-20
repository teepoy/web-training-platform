from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterator

import polars as pl
import pyarrow.flight as flight
import pytest

from sc_upstream.cache import QueryCache
from sc_upstream.flight_server import UpstreamFlightServer


class TinyDB:
    calls = 0

    def iter_list_samples_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int = 8192,
        delay_seconds: float = 0.0,
    ) -> Iterator[pl.DataFrame]:
        self.calls += 1
        yield pl.DataFrame(
            {
                "defect_id": [1, 2],
                "wafer_key": [wafer_key, wafer_key],
            }
        )


def make_ticket() -> flight.Ticket:
    return flight.Ticket(
        json.dumps(
            {
                "type": "list_samples",
                "inspection_time": "2026-01-01T00:00:00",
                "wafer_key": 7,
            }
        ).encode()
    )


@pytest.fixture()
def redis_url() -> Iterator[str]:
    redislite = pytest.importorskip("redislite")
    try:
        redis = redislite.Redis(protocol=2)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"redislite server unavailable: {exc}")
    try:
        socket_path = redis.connection_pool.connection_kwargs["path"]
        yield f"unix://{socket_path}?protocol=2"
    finally:
        redis.shutdown()


def test_do_get_uses_real_redis_sync_lock(
    redis_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))

    db = TinyDB()
    cache = QueryCache()
    server = UpstreamFlightServer(
        db,  # type: ignore[arg-type]
        cache,
        location="grpc://127.0.0.1:0",
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()

    try:
        client = flight.FlightClient(f"grpc://127.0.0.1:{server.port}")
        first = client.do_get(make_ticket()).read_all()

        assert db.calls == 1
        assert first.num_rows == 2
        assert cache._redis_sync is not None
        assert cache.sync_get_list_samples("2026-01-01T00:00:00", 7) is not None

        second = client.do_get(make_ticket()).read_all()
        assert second.num_rows == 2
        assert db.calls == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
