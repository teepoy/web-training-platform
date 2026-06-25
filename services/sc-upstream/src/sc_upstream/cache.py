from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import threading
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, TypeVar

from diskcache import Cache
import pyarrow as pa
import polars as pl
from polars import LazyFrame

CACHE_TTL = 3600
LOCK_TTL_SECONDS = 60
LOCK_WAIT_SECONDS = 30
LOCK_POLL_SECONDS = 0.1
CACHE_SIZE_LIMIT_ENV = "SC_UPSTREAM_CACHE_SIZE_LIMIT_BYTES"
RAW_CACHE_TTL_ENV = "SC_UPSTREAM_RAW_CACHE_TTL_SECONDS"
RAW_CACHE_DIR_ENV = "SC_UPSTREAM_RAW_CACHE_DIR"
RAW_CACHE_CLEANUP_INTERVAL_ENV = "SC_UPSTREAM_RAW_CACHE_CLEANUP_INTERVAL_SECONDS"
RAW_CACHE_STALE_WRITE_ENV = "SC_UPSTREAM_RAW_CACHE_STALE_WRITE_SECONDS"
RAW_CACHE_ORPHAN_GRACE_ENV = "SC_UPSTREAM_RAW_CACHE_ORPHAN_GRACE_SECONDS"
RAW_CACHE_CLEANUP_INTERVAL_SECONDS = 7200
RAW_CACHE_STALE_WRITE_SECONDS = 300
RAW_CACHE_ORPHAN_GRACE_SECONDS = 600
_T = TypeVar("_T")

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


class RawSamplesWriter:
    def __init__(
        self,
        *,
        redis_sync: Any,
        redis_key: str,
        token: str,
        temp_dir: Path,
        final_dir: Path,
        data_path: Path,
        final_data_path: Path,
        ttl_seconds: int,
        schema: pa.Schema,
    ) -> None:
        self._redis_sync = redis_sync
        self._redis_key = redis_key
        self._token = token
        self._temp_dir = temp_dir
        self._final_dir = final_dir
        self._data_path = data_path
        self._final_data_path = final_data_path
        self._ttl_seconds = ttl_seconds
        self._writer = pa.ipc.new_file(str(data_path), schema)
        self._rows = 0
        self._created_at = int(time.time())
        self._closed = False

    def write_frame(self, df: pl.DataFrame) -> None:
        if self._closed:
            raise RuntimeError("raw samples writer is already closed")
        table = df.to_arrow()
        self._writer.write_table(table)
        self._rows += df.height
        self._write_metadata("writing")

    def finish(self) -> None:
        if self._closed:
            return
        self._writer.close()
        self._closed = True
        self._temp_dir.rename(self._final_dir)
        self._write_metadata("ready", path=self._final_data_path)

    def abort(self) -> None:
        if not self._closed:
            self._writer.close()
            self._closed = True
        self._redis_sync.delete(self._redis_key)
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _write_metadata(self, state: str, path: Path | None = None) -> None:
        now = int(time.time())
        data_path = path or self._data_path
        payload = {
            "uuid": self._token,
            "state": state,
            "rows": self._rows,
            "bytes": data_path.stat().st_size if data_path.exists() else 0,
            "created_at": self._created_at,
            "updated_at": now,
            "expires_at": now + self._ttl_seconds,
        }
        self._redis_sync.set(
            self._redis_key,
            json.dumps(payload, separators=(",", ":")),
            ex=self._ttl_seconds,
        )
        meta_path = data_path.parent / "meta.json"
        tmp_path = data_path.parent / "meta.json.tmp"
        content = json.dumps(
            {"redis_key": self._redis_key, **payload},
            separators=(",", ":"),
        )
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.rename(meta_path)


class QueryCache:
    def __init__(self, cache_dir: str | None = None) -> None:
        self._dir = cache_dir or os.environ.get("CACHE_DIR", "/tmp/sc-upstream")
        self._raw_ttl_seconds = _positive_int_env(RAW_CACHE_TTL_ENV, CACHE_TTL)
        self._raw_cleanup_interval_seconds = _positive_int_env(
            RAW_CACHE_CLEANUP_INTERVAL_ENV,
            RAW_CACHE_CLEANUP_INTERVAL_SECONDS,
        )
        self._raw_stale_write_seconds = _positive_int_env(
            RAW_CACHE_STALE_WRITE_ENV,
            RAW_CACHE_STALE_WRITE_SECONDS,
        )
        self._raw_orphan_grace_seconds = _positive_int_env(
            RAW_CACHE_ORPHAN_GRACE_ENV,
            RAW_CACHE_ORPHAN_GRACE_SECONDS,
        )
        self._raw_dir = Path(
            os.environ.get(RAW_CACHE_DIR_ENV, str(Path(self._dir) / "raw-samples"))
        )
        self._raw_tmp_dir = self._raw_dir / "tmp"
        self._raw_objects_dir = self._raw_dir / "objects"
        cache_kwargs: dict[str, int] = {}
        raw_size_limit = os.environ.get(CACHE_SIZE_LIMIT_ENV, "").strip()
        if raw_size_limit:
            try:
                size_limit = int(raw_size_limit)
            except ValueError as exc:
                raise ValueError(
                    f"{CACHE_SIZE_LIMIT_ENV} must be an integer byte count"
                ) from exc
            if size_limit <= 0:
                raise ValueError(f"{CACHE_SIZE_LIMIT_ENV} must be greater than 0")
            cache_kwargs["size_limit"] = size_limit
        self._cache = Cache(self._dir, **cache_kwargs)
        self._redis = None
        self._redis_sync = None
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if redis_url:
            try:
                from redis import asyncio as redis_asyncio
                from redis import Redis

                self._redis = redis_asyncio.from_url(redis_url, decode_responses=True)
                self._redis_sync = Redis.from_url(redis_url, decode_responses=True)
                self._redis_sync.ping()
            except Exception:
                raise
        if self._redis is None or self._redis_sync is None:
            raise RuntimeError(
                "REDIS_URL is required for sc-upstream cache coordination"
            )
        self._raw_tmp_dir.mkdir(parents=True, exist_ok=True)
        self._raw_objects_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_raw_samples_cache()
        cleanup_thread = threading.Thread(
            target=self._raw_cleanup_loop,
            name="sc-upstream-raw-cache-cleanup",
            daemon=True,
        )
        cleanup_thread.start()

    def _key(self, *parts: str) -> str:
        return ":".join(parts)

    @asynccontextmanager
    async def fill_lock(self, *parts: str) -> AsyncIterator[bool]:
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
        return await asyncio.to_thread(
            self.sync_get_list_samples, inspection_time, wafer_key
        )

    def sync_get_list_samples(
        self, inspection_time: str, wafer_key: int
    ) -> LazyFrame | None:
        key = self._key("samples", inspection_time, str(wafer_key))
        raw_meta = self._redis_sync.get(key)
        if not raw_meta:
            return None
        try:
            meta = json.loads(raw_meta)
        except json.JSONDecodeError:
            self._redis_sync.delete(key)
            return None
        if meta.get("state") != "ready":
            return None
        token = str(meta.get("uuid", ""))
        if not token:
            self._redis_sync.delete(key)
            return None
        data_path = self._raw_objects_dir / token / "data.arrow"
        if not data_path.exists():
            self._redis_sync.delete(key)
            return None
        return pl.read_ipc(data_path).lazy()

    def sync_start_list_samples_writer(
        self,
        inspection_time: str,
        wafer_key: int,
        schema: pa.Schema,
    ) -> RawSamplesWriter:
        key = self._key("samples", inspection_time, str(wafer_key))
        token = uuid.uuid4().hex
        temp_dir = self._raw_tmp_dir / token
        final_dir = self._raw_objects_dir / token
        temp_dir.mkdir(parents=True, exist_ok=False)
        writer = RawSamplesWriter(
            redis_sync=self._redis_sync,
            redis_key=key,
            token=token,
            temp_dir=temp_dir,
            final_dir=final_dir,
            data_path=temp_dir / "data.arrow",
            final_data_path=final_dir / "data.arrow",
            ttl_seconds=self._raw_ttl_seconds,
            schema=schema,
        )
        writer._write_metadata("writing")
        return writer

    def _raw_cleanup_loop(self) -> None:
        while True:
            time.sleep(self._raw_cleanup_interval_seconds)
            self._cleanup_raw_samples_cache()

    def _cleanup_raw_samples_cache(self) -> None:
        now = time.time()
        for path in self._raw_tmp_dir.iterdir() if self._raw_tmp_dir.exists() else []:
            if not self._is_stale_temp_dir(path, now):
                continue
            shutil.rmtree(path, ignore_errors=True)

        for path in (
            self._raw_objects_dir.iterdir() if self._raw_objects_dir.exists() else []
        ):
            if not path.is_dir():
                continue
            if self._is_recent(path, now, self._raw_orphan_grace_seconds):
                continue
            meta_path = path / "meta.json"
            if not meta_path.exists():
                shutil.rmtree(path, ignore_errors=True)
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                shutil.rmtree(path, ignore_errors=True)
                continue
            redis_key = meta.get("redis_key")
            raw_redis_meta = self._redis_sync.get(redis_key) if redis_key else None
            if not raw_redis_meta:
                shutil.rmtree(path, ignore_errors=True)
                continue
            try:
                redis_meta = json.loads(raw_redis_meta)
            except json.JSONDecodeError:
                self._redis_sync.delete(redis_key)
                shutil.rmtree(path, ignore_errors=True)
                continue
            if redis_meta.get("expires_at", now + 1) < now:
                self._redis_sync.delete(redis_key)
                shutil.rmtree(path, ignore_errors=True)
                continue
            if redis_meta.get("state") in {"failed", "writing"} and (
                float(redis_meta.get("updated_at", 0)) + self._raw_stale_write_seconds
                < now
            ):
                self._redis_sync.delete(redis_key)
                shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def _is_recent(path: Path, now: float, threshold_seconds: int) -> bool:
        try:
            return path.stat().st_mtime + threshold_seconds >= now
        except FileNotFoundError:
            return False

    def _is_stale_temp_dir(self, path: Path, now: float) -> bool:
        meta_path = path / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                updated_at = float(meta.get("updated_at", 0))
                return updated_at + self._raw_stale_write_seconds < now
            except (ValueError, json.JSONDecodeError):
                return True
        return not self._is_recent(path, now, self._raw_stale_write_seconds)

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
