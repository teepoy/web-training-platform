from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Protocol

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    generate_latest,
)


class RedisLike(Protocol):
    def pfadd(self, name: str, *values: str) -> object: ...

    def expire(self, name: str, time: int) -> object: ...

    def pfcount(self, *names: str) -> object: ...


class OnlineJwtUsersCollector:
    """Track unique JWT users observed in the current hourly window.

    With Redis configured this uses HyperLogLog, so all uvicorn workers share a
    low-overhead approximate unique count.  Without Redis it falls back to a
    per-process in-memory set, which is intentionally approximate under
    multi-worker uvicorn but avoids adding request-path I/O.
    """

    def __init__(
        self,
        *,
        window: timedelta = timedelta(hours=1),
        redis_client: RedisLike | None = None,
        key_prefix: str = "finetune:metrics:online-jwt-users",
    ) -> None:
        self._window = window
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._lock = Lock()
        self._window_started_at = self._now()
        self._user_ids: set[str] = set()
        self._registry = CollectorRegistry()
        self._gauge = Gauge(
            "finetune_online_jwt_users",
            "Unique JWT users observed during the current hourly window.",
            registry=self._registry,
        )

    def configure_redis(self, redis_client: RedisLike | None) -> None:
        self._redis = redis_client

    async def close(self) -> None:
        close = getattr(self._redis, "aclose", None) or getattr(
            self._redis, "close", None
        )
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result

    async def observe_user(self, user_id: str) -> None:
        if not user_id:
            return
        with self._lock:
            self._roll_window_locked()
            if user_id in self._user_ids:
                return
            self._user_ids.add(user_id)

        redis_client = self._redis
        if redis_client is not None:
            key = self._current_redis_key()
            try:
                await self._maybe_await(redis_client.pfadd(key, user_id))
                await self._maybe_await(
                    redis_client.expire(key, int(self._window.total_seconds()) * 2)
                )
                return
            except Exception:
                pass

    async def count(self) -> int:
        redis_client = self._redis
        if redis_client is not None:
            try:
                value = await self._maybe_await(
                    redis_client.pfcount(self._current_redis_key())
                )
                if isinstance(value, int | float | str):
                    return int(value)
            except Exception:
                pass

        with self._lock:
            self._roll_window_locked()
            return len(self._user_ids)

    async def render_prometheus(self) -> bytes:
        self._gauge.set(await self.count())
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST

    def reset(self) -> None:
        with self._lock:
            self._window_started_at = self._now()
            self._user_ids.clear()

    def _roll_window_locked(self) -> None:
        now = self._now()
        if now - self._window_started_at >= self._window:
            self._window_started_at = now
            self._user_ids.clear()

    def _current_redis_key(self) -> str:
        now = self._now()
        bucket = now.strftime("%Y%m%d%H")
        return f"{self._key_prefix}:{bucket}"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def _maybe_await(self, value: object) -> object:
        if hasattr(value, "__await__"):
            return await value  # type: ignore[misc]
        return value


online_jwt_users = OnlineJwtUsersCollector()
