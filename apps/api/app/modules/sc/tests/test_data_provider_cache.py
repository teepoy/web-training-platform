from __future__ import annotations

import asyncio
import fnmatch
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.core.config import ScDataProviderConfig, load_config
from app.modules.sc.data_provider.cache import ScDataObjectCache


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}

    async def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            deleted += int(self.values.pop(name, None) is not None)
        return deleted

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: str
    ) -> int:
        del numkeys
        key, token = keys_and_args[:2]
        if self.values.get(key) != token:
            return 0
        if "expire" in script:
            return 1
        await self.delete(key)
        return 1

    async def exists(self, *names: str) -> int:
        return sum(name in self.values for name in names)

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        del ex
        if nx and name in self.values:
            return False
        self.values[name] = value
        return True

    async def zadd(self, name: str, mapping: dict[str, float]) -> int:
        self.sorted_sets.setdefault(name, {}).update(mapping)
        return len(mapping)

    async def zrange(
        self, name: str, start: int, end: int
    ) -> list[bytes | str]:
        members: list[bytes | str] = [
            member
            for member, _score in sorted(
                self.sorted_sets.get(name, {}).items(), key=lambda item: item[1]
            )
        ]
        return members[start:] if end == -1 else members[start : end + 1]

    async def zrem(self, name: str, *values: str) -> int:
        target = self.sorted_sets.setdefault(name, {})
        deleted = 0
        for value in values:
            deleted += int(target.pop(value, None) is not None)
        return deleted

    async def zscore(self, name: str, value: str) -> float | None:
        return self.sorted_sets.get(name, {}).get(value)

    async def scan_iter(self, *, match: str) -> AsyncIterator[str]:
        for key in list(self.values):
            if fnmatch.fnmatchcase(key, match):
                yield key


def _config(tmp_path: Path, **updates: Any) -> ScDataProviderConfig:
    return load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={
            "cache_dir": str(tmp_path),
            "cache_namespace": "cache-test",
            "revision_namespace": "cache-test",
            "build_poll_interval_ms": 1,
            "build_wait_timeout_seconds": 2,
            **updates,
        }
    )


@pytest.mark.asyncio
async def test_cache_build_is_single_flight_and_second_reader_hits(
    tmp_path: Path,
) -> None:
    redis = _FakeRedis()
    cache = ScDataObjectCache(redis, config=_config(tmp_path))
    await cache.initialize()
    started = asyncio.Event()
    release = asyncio.Event()
    builds = 0

    async def builder() -> pa.Table:
        nonlocal builds
        builds += 1
        started.set()
        await release.wait()
        return pa.table({"defect_id": [1, 2]})

    first = asyncio.create_task(
        cache.get_or_build(
            logical_key="inspection:one:samples",
            scope="org:o:inspection:one",
            revision=0,
            builder=builder,
        )
    )
    await started.wait()
    second = asyncio.create_task(
        cache.get_or_build(
            logical_key="inspection:one:samples",
            scope="org:o:inspection:one",
            revision=0,
            builder=builder,
        )
    )
    release.set()
    built, waited = await asyncio.gather(first, second)

    assert builds == 1
    assert built.object_id == waited.object_id
    assert {built.cache_status, waited.cache_status} == {"miss", "hit-wait"}
    assert built.path.is_file()
    assert not list((tmp_path / "tmp").iterdir())


@pytest.mark.asyncio
async def test_cache_file_builder_publishes_streamed_parquet(tmp_path: Path) -> None:
    redis = _FakeRedis()
    cache = ScDataObjectCache(redis, config=_config(tmp_path))
    await cache.initialize()

    async def builder(path: Path) -> None:
        await asyncio.to_thread(
            pq.write_table,
            pa.table({"defect_id": [1, 2, 3]}),
            path,
        )

    cached = await cache.get_or_build_file(
        logical_key="inspection:streamed:samples",
        scope="org:o:inspection:streamed",
        revision=0,
        builder=builder,
    )

    assert pq.read_table(cached.path).column("defect_id").to_pylist() == [1, 2, 3]
    assert not list((tmp_path / "tmp").iterdir())


@pytest.mark.asyncio
async def test_cleanup_preserves_leased_old_revision_then_removes_it(
    tmp_path: Path,
) -> None:
    redis = _FakeRedis()
    config = _config(tmp_path)
    cache = ScDataObjectCache(redis, config=config)
    await cache.initialize()
    cached = await cache.get_or_build(
        logical_key="dataset:one:overlay",
        scope="org:o:dataset:one",
        revision=1,
        builder=lambda: asyncio.sleep(0, result=pa.table({"defect_id": [1]})),
    )
    await redis.set("cache-test:revision:dataset:one", "2")

    async with cache.lease([cached]):
        assert await cache.cleanup_once()
        assert cached.path.is_file()
        assert await redis.get("cache-test:cleanup-leader") is None

    assert await cache.cleanup_once()
    assert not cached.path.exists()
    assert await redis.get(f"cache-test:object:{cached.object_id}") is None


@pytest.mark.asyncio
async def test_cleanup_keeps_content_addressed_base_after_public_revision_changes(
    tmp_path: Path,
) -> None:
    redis = _FakeRedis()
    cache = ScDataObjectCache(redis, config=_config(tmp_path))
    await cache.initialize()
    cached = await cache.get_or_build(
        logical_key="dataset:one:samples-base",
        scope="org:o:dataset:one",
        revision=0,
        revision_tracked=False,
        builder=lambda: asyncio.sleep(0, result=pa.table({"defect_id": [1]})),
    )
    await redis.set("cache-test:revision:dataset:one", "50")

    assert await cache.cleanup_once()
    assert cached.path.is_file()


@pytest.mark.asyncio
async def test_cleanup_removes_stale_write_invalid_metadata_and_orphan(
    tmp_path: Path,
) -> None:
    redis = _FakeRedis()
    config = _config(tmp_path, stale_write_seconds=1)
    cache = ScDataObjectCache(redis, config=config)
    await cache.initialize()
    stale_tmp = tmp_path / "tmp" / "stale.parquet"
    orphan = tmp_path / "objects" / "orphan.parquet"
    stale_tmp.write_bytes(b"partial")
    orphan.write_bytes(b"orphan")
    old = time.time() - 2
    os.utime(stale_tmp, (old, old))
    os.utime(orphan, (old, old))
    await redis.set("cache-test:object:broken", "not-json")

    assert await cache.cleanup_once()

    assert not stale_tmp.exists()
    assert not orphan.exists()
    assert await redis.get("cache-test:object:broken") is None


@pytest.mark.asyncio
async def test_watermark_evicts_lru_until_low_watermark(tmp_path: Path) -> None:
    redis = _FakeRedis()
    config = _config(
        tmp_path,
        object_cache_max_bytes=1,
        object_cache_low_watermark_bytes=0,
    )
    cache = ScDataObjectCache(redis, config=config)
    await cache.initialize()
    first = await cache.get_or_build(
        logical_key="one",
        scope="org:o:inspection:one",
        revision=0,
        builder=lambda: asyncio.sleep(0, result=pa.table({"defect_id": [1]})),
    )
    await asyncio.sleep(0.001)
    second = await cache.get_or_build(
        logical_key="two",
        scope="org:o:inspection:two",
        revision=0,
        builder=lambda: asyncio.sleep(0, result=pa.table({"defect_id": [2]})),
    )

    assert await cache.cleanup_once()

    assert not first.path.exists()
    assert not second.path.exists()
