from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, cast

_DEFAULT_CACHE_DIR = os.environ.get("SC_PATCH_CACHE_DIR", "/tmp/sc-patch-cache")
_DEFAULT_TTL_SECONDS = int(os.environ.get("SC_CACHE_TTL_SECONDS", "1200"))
_DEFAULT_MAX_SIZE_BYTES = int(os.environ.get("SC_CACHE_MAX_SIZE_BYTES", "5368709120"))
_DEFAULT_LOCK_TTL_SECONDS = int(os.environ.get("SC_CACHE_LOCK_TTL_SECONDS", "300"))


class CacheError(Exception):
    pass


class CacheFetchError(CacheError):
    pass


class CacheLockTimeout(CacheError):
    pass


class PatchCacheProtocol(Protocol):
    """Structural interface shared by PatchImageCache and RedisPatchImageCache."""

    async def get_image(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        fetcher: Callable[..., bytes | Awaitable[bytes]] | None = None,
    ) -> bytes: ...

    def clear(self) -> None: ...


class PatchImageCache:
    """Disk-based image cache with TTL, lock dedup, and max size enforcement."""

    def __init__(
        self,
        cache_dir: str | None = None,
        ttl_seconds: int | None = None,
        max_size_bytes: int | None = None,
        lock_ttl_seconds: int | None = None,
        data_dir: str | None = None,
    ) -> None:
        if cache_dir is None:
            cache_dir = os.environ.get("SC_PATCH_CACHE_DIR")
        if cache_dir is None and data_dir:
            cache_dir = str(Path(data_dir) / "sc-patch-cache")
        self._cache_dir = Path(cache_dir or _DEFAULT_CACHE_DIR)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
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
        self._locks: dict[str, asyncio.Lock] = {}

    def _cache_key(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
    ) -> str:
        safe_time = inspection_time.replace("/", "_").replace(":", "_")
        return f"{safe_time}_{wafer_key}_{defect_id}_{image_type}.png"

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / key

    def _is_valid(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        mtime = file_path.stat().st_mtime
        return (time.time() - mtime) < self._ttl_seconds

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get_image(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        fetcher: Callable[..., bytes | Awaitable[bytes]] | None = None,
    ) -> bytes:
        key = self._cache_key(inspection_time, wafer_key, defect_id, image_type)
        file_path = self._cache_path(key)

        if self._is_valid(file_path):
            return file_path.read_bytes()

        lock = self._get_lock(key)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=self._lock_ttl_seconds)
        except asyncio.TimeoutError:
            raise CacheLockTimeout(f"Timed out waiting for cache lock for key: {key}")

        try:
            if self._is_valid(file_path):
                return file_path.read_bytes()

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

            tmp_path = file_path.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.rename(file_path)

            await asyncio.to_thread(self._evict_if_needed)

            return data

        finally:
            lock.release()

    def _evict_if_needed(self) -> None:
        total_size = sum(
            f.stat().st_size
            for f in self._cache_dir.iterdir()
            if f.is_file() and not f.name.endswith(".tmp")
        )
        if total_size <= self._max_size_bytes:
            return

        files = [
            f
            for f in self._cache_dir.iterdir()
            if f.is_file() and not f.name.endswith(".tmp")
        ]
        files.sort(key=lambda f: f.stat().st_mtime)

        for f in files:
            if total_size <= self._max_size_bytes:
                break
            total_size -= f.stat().st_size
            f.unlink(missing_ok=True)

    def clear(self) -> None:
        for f in self._cache_dir.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
        self._locks.clear()

    def cleanup_stale_locks(self) -> None:
        now = time.time()
        for f in self._cache_dir.glob("*.lock"):
            if (now - f.stat().st_mtime) > self._lock_ttl_seconds:
                f.unlink(missing_ok=True)
