from __future__ import annotations

import json
import os
import threading
import time
import types
from datetime import datetime
from pathlib import Path
from typing import Iterator

import polars as pl
import pyarrow.flight as flight
import pytest

from sc_upstream.cache import QueryCache
from sc_upstream.flight_server import UpstreamFlightServer


class _FakeRedis:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def set(self, key: str, value: str, **kwargs) -> bool:
        self.items[key] = value
        return True

    def delete(self, key: str) -> None:
        self.items.pop(key, None)

    def ping(self) -> bool:
        return True


def _install_fake_redis(
    monkeypatch: pytest.MonkeyPatch,
    redis: _FakeRedis | None = None,
) -> _FakeRedis:
    fake = redis or _FakeRedis()

    monkeypatch.setenv("REDIS_URL", "redis://fake")
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        types.SimpleNamespace(
            Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: fake),
            asyncio=types.SimpleNamespace(from_url=lambda *args, **kwargs: fake),
        ),
    )
    return fake


def test_query_cache_uses_configured_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_redis(monkeypatch)
    monkeypatch.setenv("SC_UPSTREAM_CACHE_SIZE_LIMIT_BYTES", "1048576")

    cache = QueryCache(cache_dir=str(tmp_path / "cache"))

    assert cache._cache.size_limit == 1048576


def test_query_cache_rejects_invalid_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_redis(monkeypatch)
    monkeypatch.setenv("SC_UPSTREAM_CACHE_SIZE_LIMIT_BYTES", "0")

    with pytest.raises(ValueError, match="greater than 0"):
        QueryCache(cache_dir=str(tmp_path / "cache"))


def test_query_cache_requires_redis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        QueryCache(cache_dir=str(tmp_path / "cache"))


def test_query_cache_raw_samples_file_cache_reads_and_cleans_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SC_UPSTREAM_RAW_CACHE_ORPHAN_GRACE_SECONDS", "1")
    redis = _install_fake_redis(monkeypatch)
    cache = QueryCache(cache_dir=str(tmp_path / "cache"))
    df = pl.DataFrame(
        {
            "defect_id": [1, 2],
            "wafer_key": [7, 7],
        }
    )

    writer = cache.sync_start_list_samples_writer(
        "2026-01-01T00:00:00",
        7,
        df.to_arrow().schema,
    )
    writer.write_frame(df)
    writer.finish()

    cached = cache.sync_get_list_samples("2026-01-01T00:00:00", 7)
    assert cached is not None
    assert cached.collect().height == 2

    redis.delete("samples:2026-01-01T00:00:00:7")
    for path in cache._raw_objects_dir.iterdir():
        old = time.time() - 10
        os.utime(path, (old, old))
    cache._cleanup_raw_samples_cache()

    assert list(cache._raw_objects_dir.iterdir()) == []


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
