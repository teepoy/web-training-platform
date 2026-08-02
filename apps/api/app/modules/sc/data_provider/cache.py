from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Protocol
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import ScDataProviderConfig


_logger = logging.getLogger(__name__)


class CacheRedis(Protocol):
    async def delete(self, *names: str) -> int: ...

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any: ...

    async def exists(self, *names: str) -> int: ...

    async def get(self, name: str) -> bytes | str | None: ...

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> Any: ...

    async def zadd(self, name: str, mapping: dict[str, float]) -> int: ...

    async def zrange(self, name: str, start: int, end: int) -> list[bytes | str]: ...

    async def zrem(self, name: str, *values: str) -> int: ...

    async def zscore(self, name: str, value: str) -> float | None: ...

    def scan_iter(self, *, match: str) -> AsyncIterator[bytes | str]: ...


@dataclass(frozen=True)
class CachedDataObject:
    object_id: str
    path: Path
    size_bytes: int
    scope: str
    revision: int
    cache_status: str


@dataclass(frozen=True)
class _ObjectMetadata:
    object_id: str
    relative_path: str
    size_bytes: int
    scope: str
    revision: int
    created_at: float
    revision_tracked: bool = True


class ScDataObjectCache:
    def __init__(
        self,
        redis: CacheRedis,
        *,
        config: ScDataProviderConfig,
    ) -> None:
        self._redis = redis
        self._config = config
        self._root = Path(config.cache_dir)
        self._objects = self._root / "objects"
        self._tmp = self._root / "tmp"
        self._access_key = f"{config.cache_namespace}:object-access"

    async def initialize(self) -> None:
        await asyncio.to_thread(self._objects.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._tmp.mkdir, parents=True, exist_ok=True)

    async def get_or_build(
        self,
        *,
        logical_key: str,
        scope: str,
        revision: int,
        builder: Callable[[], Awaitable[pa.Table]],
        revision_tracked: bool = True,
        scope_revision: int | None = None,
    ) -> CachedDataObject:
        tracked_revision = self._tracked_revision(
            object_revision=revision,
            revision_tracked=revision_tracked,
            scope_revision=scope_revision,
        )
        object_id = hashlib.sha256(
            f"{logical_key}\0{revision}".encode("utf-8")
        ).hexdigest()
        cached = await self._read_valid_object(
            object_id,
            cache_status="hit",
            tracked_revision=tracked_revision,
        )
        if cached is not None:
            return cached

        lock_key = self._key("build-lock", object_id)
        lock_token = uuid4().hex
        acquired = await self._redis.set(
            lock_key,
            lock_token,
            ex=self._config.build_lock_ttl_seconds,
            nx=True,
        )
        if not acquired:
            return await self._wait_for_build(
                object_id, tracked_revision=tracked_revision
            )

        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat_owned_lock(lock_key, lock_token, heartbeat_stop),
            name=f"sc-data-build-lock-{object_id}",
        )
        try:
            cached = await self._read_valid_object(
                object_id,
                cache_status="hit",
                tracked_revision=tracked_revision,
            )
            if cached is not None:
                return cached
            table = await builder()
            return await self._write_object(
                object_id=object_id,
                scope=scope,
                revision=(
                    tracked_revision if tracked_revision is not None else revision
                ),
                table=table,
                revision_tracked=revision_tracked,
            )
        finally:
            heartbeat_stop.set()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            await self._release_owned_key(lock_key, lock_token)

    async def get_or_build_file(
        self,
        *,
        logical_key: str,
        scope: str,
        revision: int,
        builder: Callable[[Path], Awaitable[None]],
        revision_tracked: bool = True,
        scope_revision: int | None = None,
    ) -> CachedDataObject:
        """Build a Parquet object directly on disk without a full Arrow table."""
        tracked_revision = self._tracked_revision(
            object_revision=revision,
            revision_tracked=revision_tracked,
            scope_revision=scope_revision,
        )
        object_id = hashlib.sha256(
            f"{logical_key}\0{revision}".encode("utf-8")
        ).hexdigest()
        cached = await self._read_valid_object(
            object_id,
            cache_status="hit",
            tracked_revision=tracked_revision,
        )
        if cached is not None:
            return cached

        lock_key = self._key("build-lock", object_id)
        lock_token = uuid4().hex
        acquired = await self._redis.set(
            lock_key,
            lock_token,
            ex=self._config.build_lock_ttl_seconds,
            nx=True,
        )
        if not acquired:
            return await self._wait_for_build(
                object_id, tracked_revision=tracked_revision
            )

        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat_owned_lock(lock_key, lock_token, heartbeat_stop),
            name=f"sc-data-build-lock-{object_id}",
        )
        temporary_path = self._tmp / f"{uuid4().hex}.parquet"
        try:
            cached = await self._read_valid_object(
                object_id,
                cache_status="hit",
                tracked_revision=tracked_revision,
            )
            if cached is not None:
                return cached
            await builder(temporary_path)
            await asyncio.to_thread(pq.read_metadata, temporary_path)
            return await self._publish_object_file(
                object_id=object_id,
                scope=scope,
                revision=(
                    tracked_revision if tracked_revision is not None else revision
                ),
                temporary_path=temporary_path,
                revision_tracked=revision_tracked,
            )
        finally:
            heartbeat_stop.set()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            await self._release_owned_key(lock_key, lock_token)
            with suppress(FileNotFoundError):
                await asyncio.to_thread(temporary_path.unlink)

    @asynccontextmanager
    async def lease(self, objects: list[CachedDataObject]) -> AsyncIterator[None]:
        lease_id = uuid4().hex
        keys = [self._key("lease", item.object_id, lease_id) for item in objects]
        for key in keys:
            await self._redis.set(
                key,
                str(os.getpid()),
                ex=self._config.lease_ttl_seconds,
            )
        stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(keys, stop), name=f"sc-data-lease-{lease_id}"
        )
        try:
            yield
        finally:
            stop.set()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            if keys:
                await self._redis.delete(*keys)

    async def cleanup_once(self) -> bool:
        leader_key = self._key("cleanup-leader")
        leader_token = uuid4().hex
        acquired = await self._redis.set(
            leader_key,
            leader_token,
            ex=self._config.cleanup_interval_seconds * 2,
            nx=True,
        )
        if not acquired:
            return False
        try:
            await asyncio.to_thread(self._remove_stale_temp_files)
            objects = await self._read_all_metadata()
            await self._remove_orphan_files(objects)
            await self._remove_expired_objects(objects)
            await self._enforce_watermark()
            return True
        finally:
            await self._release_owned_key(leader_key, leader_token)

    async def run_cleanup_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.cleanup_once()
            except Exception:
                _logger.warning(
                    "SC data cache cleanup failed; Redis/filesystem retry scheduled",
                    exc_info=True,
                )
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self._config.cleanup_interval_seconds
                )
            except TimeoutError:
                pass

    async def _write_object(
        self,
        *,
        object_id: str,
        scope: str,
        revision: int,
        table: pa.Table,
        revision_tracked: bool,
    ) -> CachedDataObject:
        temporary_path = self._tmp / f"{uuid4().hex}.parquet"
        try:
            await asyncio.to_thread(pq.write_table, table, temporary_path)
            return await self._publish_object_file(
                object_id=object_id,
                scope=scope,
                revision=revision,
                temporary_path=temporary_path,
                revision_tracked=revision_tracked,
            )
        finally:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(temporary_path.unlink)

    async def _publish_object_file(
        self,
        *,
        object_id: str,
        scope: str,
        revision: int,
        temporary_path: Path,
        revision_tracked: bool,
    ) -> CachedDataObject:
        final_path = self._objects / f"{object_id}.parquet"
        await asyncio.to_thread(os.replace, temporary_path, final_path)
        size_bytes = final_path.stat().st_size
        metadata = _ObjectMetadata(
            object_id=object_id,
            relative_path=str(final_path.relative_to(self._root)),
            size_bytes=size_bytes,
            scope=scope,
            revision=revision,
            created_at=time.time(),
            revision_tracked=revision_tracked,
        )
        await self._redis.set(
            self._metadata_key(object_id), json.dumps(asdict(metadata))
        )
        await self._touch(object_id)
        return CachedDataObject(
            object_id=object_id,
            path=final_path,
            size_bytes=size_bytes,
            scope=scope,
            revision=revision,
            cache_status="miss",
        )

    async def _wait_for_build(
        self, object_id: str, *, tracked_revision: int | None
    ) -> CachedDataObject:
        deadline = time.monotonic() + self._config.build_wait_timeout_seconds
        interval = self._config.build_poll_interval_ms / 1000
        while time.monotonic() < deadline:
            cached = await self._read_valid_object(
                object_id,
                cache_status="hit-wait",
                tracked_revision=tracked_revision,
            )
            if cached is not None:
                return cached
            await asyncio.sleep(interval)
        raise TimeoutError(f"timed out waiting for cache object {object_id}")

    async def _read_valid_object(
        self,
        object_id: str,
        *,
        cache_status: str,
        tracked_revision: int | None,
    ) -> CachedDataObject | None:
        raw = await self._redis.get(self._metadata_key(object_id))
        if raw is None:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            metadata = _ObjectMetadata(**json.loads(raw))
            path = self._root / metadata.relative_path
            if (
                metadata.object_id != object_id
                or path.parent != self._objects
                or path.name != f"{object_id}.parquet"
                or not path.is_file()
                or path.stat().st_size != metadata.size_bytes
            ):
                raise ValueError("cache metadata does not match its object")
            await asyncio.to_thread(pq.read_metadata, path)
        except (OSError, pa.ArrowInvalid, TypeError, ValueError, json.JSONDecodeError):
            await self._redis.delete(self._metadata_key(object_id))
            return None
        revision = metadata.revision
        if tracked_revision is not None:
            promoted_revision = await self._promote_tracked_revision(
                object_id, tracked_revision
            )
            if promoted_revision is None:
                return None
            revision = promoted_revision
        await self._touch(object_id)
        return CachedDataObject(
            object_id=metadata.object_id,
            path=path,
            size_bytes=metadata.size_bytes,
            scope=metadata.scope,
            revision=revision,
            cache_status=cache_status,
        )

    async def _heartbeat(self, keys: list[str], stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self._config.lease_heartbeat_seconds
                )
                return
            except TimeoutError:
                try:
                    for key in keys:
                        await self._redis.set(
                            key,
                            str(os.getpid()),
                            ex=self._config.lease_ttl_seconds,
                        )
                except Exception:
                    _logger.warning(
                        "SC data cache lease heartbeat failed; retry scheduled",
                        exc_info=True,
                    )

    async def _heartbeat_owned_lock(
        self, key: str, token: str, stop: asyncio.Event
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self._config.build_lock_heartbeat_seconds
                )
                return
            except TimeoutError:
                try:
                    renewed = await self._redis.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end",
                        1,
                        key,
                        token,
                        str(self._config.build_lock_ttl_seconds),
                    )
                except Exception:
                    _logger.warning(
                        "SC data cache build-lock heartbeat failed; retry scheduled",
                        exc_info=True,
                    )
                    continue
                if not renewed:
                    raise RuntimeError(f"lost SC data cache build lock {key}")

    def _remove_stale_temp_files(self) -> None:
        cutoff = time.time() - self._config.stale_write_seconds
        for path in self._tmp.glob("*.parquet"):
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)

    async def _read_all_metadata(self) -> dict[str, _ObjectMetadata]:
        result: dict[str, _ObjectMetadata] = {}
        async for raw_key in self._redis.scan_iter(match=self._key("object", "*")):
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
            raw = await self._redis.get(key)
            try:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if raw is None:
                    continue
                metadata = _ObjectMetadata(**json.loads(raw))
                object_id = key.rsplit(":", 1)[-1]
                path = self._root / metadata.relative_path
                if (
                    metadata.object_id != object_id
                    or path.parent != self._objects
                    or path.name != f"{object_id}.parquet"
                    or not path.is_file()
                    or path.stat().st_size != metadata.size_bytes
                ):
                    raise ValueError("cache metadata does not match its object")
                await asyncio.to_thread(pq.read_metadata, path)
                result[metadata.object_id] = metadata
            except (
                OSError,
                pa.ArrowInvalid,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                await self._redis.delete(key)
        return result

    async def _remove_orphan_files(self, objects: dict[str, _ObjectMetadata]) -> None:
        known = {metadata.relative_path for metadata in objects.values()}
        cutoff = time.time() - self._config.stale_write_seconds
        for path in self._objects.glob("*.parquet"):
            relative = str(path.relative_to(self._root))
            if relative not in known and path.stat().st_mtime < cutoff:
                await asyncio.to_thread(path.unlink, missing_ok=True)

    async def _remove_expired_objects(
        self, objects: dict[str, _ObjectMetadata]
    ) -> None:
        cutoff = time.time() - self._config.object_idle_ttl_seconds
        for object_id, metadata in objects.items():
            score = await self._access_score(object_id)
            revision_key = self._revision_key_for_metadata(metadata)
            raw_current_revision = await self._redis.get(revision_key)
            is_old_revision = (
                metadata.revision_tracked
                and raw_current_revision is not None
                and metadata.revision < int(raw_current_revision)
            )
            is_idle = score is not None and score < cutoff
            if (is_old_revision or is_idle) and not await self._has_lease(object_id):
                await self._delete_object(object_id)

    async def _enforce_watermark(self) -> None:
        total = sum(path.stat().st_size for path in self._objects.glob("*.parquet"))
        if total <= self._config.object_cache_max_bytes:
            return
        for raw_object_id in await self._redis.zrange(self._access_key, 0, -1):
            object_id = (
                raw_object_id.decode("utf-8")
                if isinstance(raw_object_id, bytes)
                else raw_object_id
            )
            if await self._has_lease(object_id):
                continue
            path = self._objects / f"{object_id}.parquet"
            size = path.stat().st_size if path.exists() else 0
            await self._delete_object(object_id)
            total -= size
            if total <= self._config.object_cache_low_watermark_bytes:
                return

    async def _delete_object(self, object_id: str) -> None:
        path = self._objects / f"{object_id}.parquet"
        await asyncio.to_thread(path.unlink, missing_ok=True)
        await self._redis.delete(self._metadata_key(object_id))
        await self._redis.zrem(self._access_key, object_id)

    async def _has_lease(self, object_id: str) -> bool:
        async for _key in self._redis.scan_iter(
            match=self._key("lease", object_id, "*")
        ):
            return True
        return False

    async def _access_score(self, object_id: str) -> float | None:
        return await self._redis.zscore(self._access_key, object_id)

    async def _touch(self, object_id: str) -> None:
        now = time.time()
        await self._redis.zadd(self._access_key, {object_id: now})
        await self._redis.set(self._key("last-access", object_id), str(now))

    async def _promote_tracked_revision(
        self, object_id: str, scope_revision: int
    ) -> int | None:
        promoted = await self._redis.eval(
            "local raw = redis.call('get', KEYS[1]); "
            "if not raw then return -1 end; "
            "local metadata = cjson.decode(raw); "
            "local requested = tonumber(ARGV[1]); "
            "local current = tonumber(metadata['revision']); "
            "if not metadata['revision_tracked'] then "
            "metadata['revision_tracked'] = true; metadata['revision'] = requested; "
            "redis.call('set', KEYS[1], cjson.encode(metadata)); return requested; end; "
            "if requested > current then metadata['revision'] = requested; "
            "redis.call('set', KEYS[1], cjson.encode(metadata)); return requested; end; "
            "return current",
            1,
            self._metadata_key(object_id),
            str(scope_revision),
        )
        revision = int(promoted)
        return None if revision < 0 else revision

    @staticmethod
    def _tracked_revision(
        *,
        object_revision: int,
        revision_tracked: bool,
        scope_revision: int | None,
    ) -> int | None:
        if scope_revision is not None and scope_revision < 0:
            raise ValueError("scope_revision must be non-negative")
        if not revision_tracked:
            if scope_revision is not None:
                raise ValueError(
                    "scope_revision cannot be set when revision_tracked is false"
                )
            return None
        return object_revision if scope_revision is None else scope_revision

    async def _release_owned_key(self, key: str, token: str) -> None:
        await self._redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )

    def _metadata_key(self, object_id: str) -> str:
        return self._key("object", object_id)

    def _revision_key_for_metadata(self, metadata: _ObjectMetadata) -> str:
        parts = metadata.scope.split(":", 2)
        public_scope = (
            parts[2] if len(parts) == 3 and parts[0] == "org" else metadata.scope
        )
        return f"{self._config.revision_namespace}:revision:{public_scope}"

    def _key(self, *parts: str) -> str:
        return ":".join((self._config.cache_namespace, *parts))
