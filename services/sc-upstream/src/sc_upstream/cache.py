from __future__ import annotations

import asyncio
import io
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, TypeVar

from diskcache import Cache
import polars as pl
from polars import LazyFrame

CACHE_TTL = 3600
LOCK_TTL_SECONDS = 60
LOCK_WAIT_SECONDS = 30
LOCK_POLL_SECONDS = 0.1
_T = TypeVar("_T")

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class QueryCache:
    def __init__(self, cache_dir: str | None = None) -> None:
        self._dir = cache_dir or os.environ.get("CACHE_DIR", "/tmp/sc-upstream")
        self._cache = Cache(self._dir)
        self._redis = None
        self._redis_sync = None
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url:
            try:
                from redis import asyncio as redis_asyncio
                from redis import Redis

                self._redis = redis_asyncio.from_url(redis_url, decode_responses=True)
                self._redis_sync = Redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self._redis = None
                self._redis_sync = None

    def _key(self, *parts: str) -> str:
        return ":".join(parts)

    @asynccontextmanager
    async def fill_lock(self, *parts: str) -> AsyncIterator[bool]:
        if self._redis is None:
            yield True
            return

        key = self._key("lock", *parts)
        token = uuid.uuid4().hex
        acquired = bool(await self._redis.set(key, token, nx=True, ex=LOCK_TTL_SECONDS))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await self._redis.eval(_RELEASE_SCRIPT, 1, key, token)
                except Exception:
                    pass

    async def wait_for_fill(
        self,
        getter: Callable[[], Awaitable[_T | None]],
        *,
        timeout_seconds: float = LOCK_WAIT_SECONDS,
    ) -> _T | None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            cached = await getter()
            if cached is not None:
                return cached
            await asyncio.sleep(LOCK_POLL_SECONDS)
        return None

    @contextmanager
    def sync_fill_lock(self, *parts: str) -> Iterator[bool]:
        if self._redis_sync is None:
            yield True
            return

        key = self._key("lock", *parts)
        token = uuid.uuid4().hex
        acquired = bool(self._redis_sync.set(key, token, nx=True, ex=LOCK_TTL_SECONDS))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    self._redis_sync.eval(_RELEASE_SCRIPT, 1, key, token)
                except Exception:
                    pass

    def sync_wait_for_fill(
        self,
        getter: Callable[[], _T | None],
        *,
        timeout_seconds: float = LOCK_WAIT_SECONDS,
    ) -> _T | None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            cached = getter()
            if cached is not None:
                return cached
            time.sleep(LOCK_POLL_SECONDS)
        return None

    async def get_inspection(self, inspection_time: str, wafer_key: int) -> dict | None:
        return await asyncio.to_thread(
            self._cache.get, self._key("inspect", inspection_time, str(wafer_key))
        )

    async def set_inspection(
        self, inspection_time: str, wafer_key: int, data: dict
    ) -> None:
        await asyncio.to_thread(
            self._cache.set,
            self._key("inspect", inspection_time, str(wafer_key)),
            data,
            expire=CACHE_TTL,
        )

    async def get_list_inspections(
        self,
        start_time: str,
        end_time: str,
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> list[dict] | None:
        return await asyncio.to_thread(
            self._cache.get,
            self._key(
                "insps", start_time, end_time, lot_id, wafer_id, layer_id, device
            ),
        )

    async def set_list_inspections(
        self,
        start_time: str,
        end_time: str,
        items: list[dict],
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> None:
        await asyncio.to_thread(
            self._cache.set,
            self._key(
                "insps", start_time, end_time, lot_id, wafer_id, layer_id, device
            ),
            items,
            expire=CACHE_TTL,
        )

    async def get_list_review_images(
        self, inspection_time: str, wafer_key: int
    ) -> list[dict] | None:
        return await asyncio.to_thread(
            self._cache.get, self._key("review", inspection_time, str(wafer_key))
        )

    async def set_list_review_images(
        self, inspection_time: str, wafer_key: int, items: list[dict]
    ) -> None:
        await asyncio.to_thread(
            self._cache.set,
            self._key("review", inspection_time, str(wafer_key)),
            items,
            expire=CACHE_TTL,
        )

    async def get_list_samples(
        self, inspection_time: str, wafer_key: int
    ) -> LazyFrame | None:
        key = self._key("samples", inspection_time, str(wafer_key))
        ipc_bytes = await asyncio.to_thread(self._cache.get, key)
        if ipc_bytes is not None:
            from polars import read_ipc

            return read_ipc(io.BytesIO(ipc_bytes)).lazy()
        return None

    def sync_get_list_samples(
        self, inspection_time: str, wafer_key: int
    ) -> LazyFrame | None:
        key = self._key("samples", inspection_time, str(wafer_key))
        ipc_bytes = self._cache.get(key)
        if ipc_bytes is not None:
            from polars import read_ipc

            return read_ipc(io.BytesIO(ipc_bytes)).lazy()
        return None

    async def set_list_samples(
        self, inspection_time: str, wafer_key: int, lf: LazyFrame
    ) -> None:
        key = self._key("samples", inspection_time, str(wafer_key))
        buf = io.BytesIO()
        lf.collect().write_ipc(buf)

        def _set() -> None:
            self._cache.set(key, buf.getvalue(), expire=CACHE_TTL)

        await asyncio.to_thread(_set)

    def sync_set_list_samples_from_frames(
        self, inspection_time: str, wafer_key: int, frames: list[pl.DataFrame]
    ) -> None:
        if not frames:
            return
        key = self._key("samples", inspection_time, str(wafer_key))
        buf = io.BytesIO()
        pl.concat(frames, how="vertical").write_ipc(buf)
        self._cache.set(key, buf.getvalue(), expire=CACHE_TTL)

    async def get_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict] | None:
        return await asyncio.to_thread(
            self._cache.get,
            self._key("zips", inspection_time, lot_id, wafer_id, device, layer_id),
        )

    async def set_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
        items: list[dict],
    ) -> None:
        await asyncio.to_thread(
            self._cache.set,
            self._key("zips", inspection_time, lot_id, wafer_id, device, layer_id),
            items,
            expire=CACHE_TTL,
        )
