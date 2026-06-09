from __future__ import annotations

import asyncio
import time

import pytest

from app.modules.sc.adapter._wafer_mock.cache import CacheFetchError
from app.modules.sc.adapter._wafer_mock.redis_cache import RedisPatchImageCache


@pytest.fixture
def redis_client():
    redislite = pytest.importorskip("redislite")
    client = redislite.Redis()
    try:
        yield client
    finally:
        client.shutdown()


@pytest.mark.asyncio
async def test_cache_hit(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)
    key = cache._cache_key("2024-01-15T08:30:00", 1, "D001", "template")
    data_key = cache._data_key(key)
    redis_client.setex(data_key, 60, b"cached image data")
    cache._touch(data_key)

    call_count = 0

    def mock_fetcher() -> bytes:
        nonlocal call_count
        call_count += 1
        return b"should not be called"

    data = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=mock_fetcher,
    )
    assert data == b"cached image data"
    assert call_count == 0
    cache.clear()


@pytest.mark.asyncio
async def test_cache_miss_no_fetcher(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)
    with pytest.raises(CacheFetchError, match="no fetcher"):
        await cache.get_image(
            "2024-01-15T08:30:00",
            1,
            "D001",
            "template",
        )
    cache.clear()


@pytest.mark.asyncio
async def test_cache_miss_with_fetcher(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)
    call_count = 0

    def mock_fetcher() -> bytes:
        nonlocal call_count
        call_count += 1
        return b"fresh data"

    data = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=mock_fetcher,
    )
    assert data == b"fresh data"
    assert call_count == 1
    cache.clear()


@pytest.mark.asyncio
async def test_cache_ttl_expiry(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=1)
    call_count = 0

    def mock_fetcher() -> bytes:
        nonlocal call_count
        call_count += 1
        return b"re-fetched"

    data1 = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=mock_fetcher,
    )
    assert data1 == b"re-fetched"
    assert call_count == 1

    data2 = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=mock_fetcher,
    )
    assert data2 == b"re-fetched"
    assert call_count == 1

    await asyncio.sleep(1.1)
    data3 = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=mock_fetcher,
    )
    assert data3 == b"re-fetched"
    assert call_count == 2
    cache.clear()


@pytest.mark.asyncio
async def test_cache_concurrent_dedup(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)
    call_count = 0

    def mock_fetcher() -> bytes:
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return b"shared data"

    tasks = [
        cache.get_image(
            "2024-01-15T08:30:00",
            1,
            "D001",
            "template",
            fetcher=mock_fetcher,
        )
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)

    assert call_count == 1
    assert all(r == b"shared data" for r in results)
    cache.clear()


@pytest.mark.asyncio
async def test_cache_no_poison_on_failure(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)

    def bad_fetcher() -> bytes:
        raise RuntimeError("S3 is down")

    with pytest.raises(CacheFetchError, match="S3 is down"):
        await cache.get_image(
            "2024-01-15T08:30:00",
            1,
            "D001",
            "template",
            fetcher=bad_fetcher,
        )

    def good_fetcher() -> bytes:
        return b"recovered"

    data = await cache.get_image(
        "2024-01-15T08:30:00",
        1,
        "D001",
        "template",
        fetcher=good_fetcher,
    )
    assert data == b"recovered"
    cache.clear()


@pytest.mark.asyncio
async def test_cache_clear(redis_client) -> None:
    cache = RedisPatchImageCache(redis_client=redis_client, ttl_seconds=60)

    for i in range(3):
        key = cache._cache_key("2024-01-15T08:30:00", 1, f"D{i:03d}", "template")
        data_key = cache._data_key(key)
        redis_client.setex(data_key, 60, b"data")
        cache._touch(data_key)

    assert redis_client.zcard(cache._index_key) == 3
    cache.clear()
    assert redis_client.zcard(cache._index_key) == 0
