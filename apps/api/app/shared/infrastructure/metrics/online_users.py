from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Protocol

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

    def hset(self, name: str, key: str, value: str) -> object: ...

    def hget(self, name: str, key: str) -> object: ...

    def hgetall(self, name: str) -> object: ...


@dataclass(frozen=True)
class ObservedJwtUser:
    id: str
    email: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class DailyJwtUserDetail:
    id: str
    email: str | None
    name: str | None
    first_seen_at: str
    last_seen_at: str


class OnlineJwtUsersCollector:
    """Track JWT users observed in operational windows.

    Redis uses minute HyperLogLog buckets for the rolling hourly count and a
    daily hash for detail snapshots.  The in-memory fallback is per-process and
    intentionally approximate under multi-worker uvicorn.
    """

    def __init__(
        self,
        *,
        window: timedelta = timedelta(hours=1),
        redis_client: RedisLike | None = None,
        key_prefix: str = "finetune:metrics:online-jwt-users",
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._window = window
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._now_factory = now_factory
        self._lock = Lock()
        self._observed: dict[str, DailyJwtUserDetail] = {}
        self._registry = CollectorRegistry()
        self._hourly_gauge = Gauge(
            "finetune_online_jwt_users",
            "Unique JWT users observed during the rolling hourly window.",
            registry=self._registry,
        )
        self._daily_gauge = Gauge(
            "finetune_daily_jwt_users",
            "Unique JWT users observed during the current UTC day.",
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

    async def observe_user(
        self,
        user: str | ObservedJwtUser,
        *,
        email: str | None = None,
        name: str | None = None,
    ) -> None:
        observed = (
            user
            if isinstance(user, ObservedJwtUser)
            else ObservedJwtUser(id=user, email=email, name=name)
        )
        if not observed.id:
            return
        now = self._now()
        timestamp = now.isoformat()
        with self._lock:
            self._roll_daily_locked(now)
            previous = self._observed.get(observed.id)
            self._observed[observed.id] = DailyJwtUserDetail(
                id=observed.id,
                email=observed.email or (previous.email if previous else None),
                name=observed.name or (previous.name if previous else None),
                first_seen_at=previous.first_seen_at if previous else timestamp,
                last_seen_at=timestamp,
            )

        redis_client = self._redis
        if redis_client is not None:
            minute_key = self._minute_redis_key(now)
            daily_key = self._daily_redis_key(now)
            try:
                await self._maybe_await(redis_client.pfadd(minute_key, observed.id))
                await self._maybe_await(
                    redis_client.expire(
                        minute_key, int(self._window.total_seconds()) * 2
                    )
                )
                first_seen_at = timestamp
                previous_payload = await self._maybe_await(
                    redis_client.hget(daily_key, observed.id)
                )
                if previous_payload:
                    first_seen_at = self._first_seen_from_redis_payload(
                        previous_payload,
                        default=timestamp,
                    )
                await self._maybe_await(
                    redis_client.hset(
                        daily_key,
                        observed.id,
                        json.dumps(
                            {
                                "id": observed.id,
                                "email": observed.email,
                                "name": observed.name,
                                "first_seen_at": first_seen_at,
                                "last_seen_at": timestamp,
                            },
                            sort_keys=True,
                        ),
                    )
                )
                await self._maybe_await(
                    redis_client.expire(
                        daily_key, int(timedelta(days=2).total_seconds())
                    )
                )
                return
            except Exception:
                pass

    async def count(self) -> int:
        return await self.hourly_count()

    async def hourly_count(self) -> int:
        redis_client = self._redis
        if redis_client is not None:
            try:
                value = await self._maybe_await(
                    redis_client.pfcount(*self._rolling_minute_keys())
                )
                if isinstance(value, int | float | str):
                    return int(value)
            except Exception:
                pass

        with self._lock:
            cutoff = self._now() - self._window
            return sum(
                1
                for detail in self._observed.values()
                if datetime.fromisoformat(detail.last_seen_at) >= cutoff
            )

    async def daily_count(self) -> int:
        return len(await self.daily_users())

    async def daily_users(self) -> list[DailyJwtUserDetail]:
        redis_client = self._redis
        if redis_client is not None:
            try:
                raw = await self._maybe_await(
                    redis_client.hgetall(self._daily_redis_key())
                )
                if isinstance(raw, dict):
                    return sorted(
                        self._decode_redis_daily_users(raw),
                        key=lambda item: item.last_seen_at,
                        reverse=True,
                    )
            except Exception:
                pass

        with self._lock:
            self._roll_daily_locked(self._now())
            return sorted(
                self._observed.values(),
                key=lambda item: item.last_seen_at,
                reverse=True,
            )

    async def render_prometheus(self) -> bytes:
        self._hourly_gauge.set(await self.hourly_count())
        self._daily_gauge.set(await self.daily_count())
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST

    def reset(self) -> None:
        with self._lock:
            self._observed.clear()

    def _roll_daily_locked(self, now: datetime) -> None:
        current_day = now.strftime("%Y%m%d")
        self._observed = {
            user_id: detail
            for user_id, detail in self._observed.items()
            if datetime.fromisoformat(detail.last_seen_at).strftime("%Y%m%d")
            == current_day
        }

    def _minute_redis_key(self, when: datetime) -> str:
        bucket = when.strftime("%Y%m%d%H%M")
        return f"{self._key_prefix}:minute:{bucket}"

    def _daily_redis_key(self, when: datetime | None = None) -> str:
        bucket = (when or self._now()).strftime("%Y%m%d")
        return f"{self._key_prefix}:day:{bucket}"

    def _rolling_minute_keys(self) -> list[str]:
        now = self._now()
        minutes = max(1, int(self._window.total_seconds() // 60))
        return [
            self._minute_redis_key(now - timedelta(minutes=offset))
            for offset in range(minutes)
        ]

    def _now(self) -> datetime:
        if self._now_factory is not None:
            return self._now_factory()
        return datetime.now(timezone.utc)

    async def _maybe_await(self, value: object) -> object:
        if hasattr(value, "__await__"):
            return await value  # type: ignore[misc]
        return value

    def _decode_redis_daily_users(
        self, values: dict[object, object]
    ) -> list[DailyJwtUserDetail]:
        users: list[DailyJwtUserDetail] = []
        for raw_user_id, raw_payload in values.items():
            user_id = self._decode_redis_value(raw_user_id)
            payload_text = self._decode_redis_value(raw_payload)
            try:
                payload = json.loads(payload_text)
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            last_seen_at = str(payload.get("last_seen_at") or self._now().isoformat())
            first_seen_at = str(payload.get("first_seen_at") or last_seen_at)
            users.append(
                DailyJwtUserDetail(
                    id=str(payload.get("id") or user_id),
                    email=payload.get("email")
                    if isinstance(payload.get("email"), str)
                    else None,
                    name=payload.get("name")
                    if isinstance(payload.get("name"), str)
                    else None,
                    first_seen_at=first_seen_at,
                    last_seen_at=last_seen_at,
                )
            )
        return users

    def _decode_redis_value(self, value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def _first_seen_from_redis_payload(self, value: object, *, default: str) -> str:
        try:
            payload = json.loads(self._decode_redis_value(value))
        except Exception:
            return default
        if not isinstance(payload, dict):
            return default
        first_seen_at = payload.get("first_seen_at")
        return first_seen_at if isinstance(first_seen_at, str) else default


online_jwt_users = OnlineJwtUsersCollector()
