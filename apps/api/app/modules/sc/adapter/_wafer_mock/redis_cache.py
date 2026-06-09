from __future__ import annotations

import asyncio
import os
import time
from contextlib import suppress
from collections.abc import Awaitable, Callable
from typing import cast

import redis
from redis.exceptions import LockError

from .cache import CacheFetchError, CacheLockTimeout

_DEFAULT_TTL_SECONDS = int(os.environ.get("SC_CACHE_TTL_SECONDS", "1200"))
_DEFAULT_MAX_SIZE_BYTES = int(os.environ.get("SC_CACHE_MAX_SIZE_BYTES", "5368709120"))
_DEFAULT_LOCK_TTL_SECONDS = int(os.environ.get("SC_CACHE_LOCK_TTL_SECONDS", "300"))
_DEFAULT_REDIS_PREFIX = os.environ.get("SC_CACHE_REDIS_PREFIX", "sc:patch-cache")


class RedisPatchImageCache:
    """Redis-based image cache with TTL, distributed lock dedup, and max size enforcement."""

    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_seconds: int | None = None,
        max_size_bytes: int | None = None,
        lock_ttl_seconds: int | None = None,
        key_prefix: str | None = None,
    ) -> None:
        self._ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS
        )
        self._max_size_bytes = (
            max_size_bytes if max_size_bytes is not None else _DEFAULT_MAX_SIZE_BYTES
        )
        self._lock_ttl_seconds = (
            lock_ttl_seconds
            if lock_ttl_seconds is not None
            else _DEFAULT_LOCK_TTL_SECONDS
        )
        self._key_prefix = key_prefix or _DEFAULT_REDIS_PREFIX
        self._redis = redis_client
        self._index_key = f"{self._key_prefix}:index"

    def _cache_key(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
    ) -> str:
        safe_time = inspection_time.replace("/", "_").replace(":", "_")
        return f"{safe_time}_{wafer_key}_{defect_id}_{image_type}.png"

    def _data_key(self, key: str) -> str:
        return f"{self._key_prefix}:data:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._key_prefix}:lock:{key}"

    def _touch(self, data_key: str) -> None:
        self._redis.zadd(self._index_key, {data_key: time.time()})

    def _evict_if_needed(self) -> None:
        raw_keys = cast(list[bytes], self._redis.zrange(self._index_key, 0, -1))
        data_keys = [k.decode("utf-8") for k in raw_keys]
        if not data_keys:
            return

        total_size = 0
        sizes: dict[str, int] = {}
        stale: list[str] = []
        for data_key in data_keys:
            size = cast(int, self._redis.strlen(data_key))
            exists = bool(self._redis.exists(data_key))
            if size == 0 and not exists:
                stale.append(data_key)
                continue
            sizes[data_key] = size
            total_size += size

        if stale:
            self._redis.zrem(self._index_key, *stale)

        if total_size <= self._max_size_bytes:
            return

        for data_key in data_keys:
            if total_size <= self._max_size_bytes:
                break
            size = sizes.get(data_key)
            if size is None:
                continue
            total_size -= size
            pipe = self._redis.pipeline()
            pipe.delete(data_key)
            pipe.zrem(self._index_key, data_key)
            pipe.execute()

    async def get_image(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        fetcher: Callable[..., bytes | Awaitable[bytes]] | None = None,
    ) -> bytes:
        key = self._cache_key(inspection_time, wafer_key, defect_id, image_type)
        data_key = self._data_key(key)
        lock_key = self._lock_key(key)

        cached = await asyncio.to_thread(self._redis.get, data_key)
        if cached is not None:
            await asyncio.to_thread(self._touch, data_key)
            return cast(bytes, cached)

        lock = self._redis.lock(
            lock_key,
            timeout=self._lock_ttl_seconds,
            blocking_timeout=self._lock_ttl_seconds,
            thread_local=False,
        )

        acquired = await asyncio.to_thread(lock.acquire, True)
        if not acquired:
            raise CacheLockTimeout(f"Timed out waiting for cache lock for key: {key}")

        try:
            cached = await asyncio.to_thread(self._redis.get, data_key)
            if cached is not None:
                await asyncio.to_thread(self._touch, data_key)
                return cast(bytes, cached)

            if fetcher is None:
                raise CacheFetchError(
                    f"Cache miss for key '{key}' and no fetcher provided"
                )

            try:
                if asyncio.iscoroutinefunction(fetcher):
                    data = await fetcher()
                else:
                    result = await asyncio.to_thread(fetcher)
                    if asyncio.iscoroutine(result):
                        data = await result
                    else:
                        data = cast(bytes, result)
            except Exception as e:
                raise CacheFetchError(
                    f"Failed to fetch data for key '{key}': {e}"
                ) from e

            def _store() -> None:
                pipe = self._redis.pipeline()
                pipe.setex(data_key, self._ttl_seconds, data)
                pipe.zadd(self._index_key, {data_key: time.time()})
                pipe.execute()
                self._evict_if_needed()

            await asyncio.to_thread(_store)
            return data
        finally:
            with suppress(LockError):
                await asyncio.to_thread(lock.release)

    def clear(self) -> None:
        raw_keys = cast(list[bytes], self._redis.zrange(self._index_key, 0, -1))
        data_keys = [k.decode("utf-8") for k in raw_keys]
        if data_keys:
            self._redis.delete(*data_keys)
        self._redis.delete(self._index_key)

    def cleanup_stale_locks(self) -> None:
        # Redis lock keys expire automatically via lock timeout.
        return
