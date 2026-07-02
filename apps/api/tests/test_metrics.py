from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.app.services.auth_service import create_access_token
from app.shared.infrastructure.metrics import online_jwt_users
from app.shared.infrastructure.metrics.online_users import OnlineJwtUsersCollector


def test_metrics_counts_unique_jwt_users_without_user_labels() -> None:
    online_jwt_users.reset()
    token_a = create_access_token({"sub": "user-a"})
    token_b = create_access_token({"sub": "user-b"})

    with TestClient(app) as client:
        client.get("/health", headers={"Authorization": f"Bearer {token_a}"})
        client.get("/ready", headers={"Authorization": f"Bearer {token_a}"})
        client.get("/health", headers={"Authorization": f"Bearer {token_b}"})
        response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "finetune_online_jwt_users 2.0" in body
    assert "user-a" not in body
    assert "user-b" not in body


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.pfadd_calls = 0

    async def pfadd(self, name: str, *values: str) -> int:
        self.pfadd_calls += 1
        bucket = self.values.setdefault(name, set())
        before = len(bucket)
        bucket.update(values)
        return len(bucket) - before

    async def expire(self, name: str, time: int) -> bool:
        return True

    async def pfcount(self, *names: str) -> int:
        combined: set[str] = set()
        for name in names:
            combined.update(self.values.get(name, set()))
        return len(combined)

    async def hset(self, name: str, key: str, value: str) -> int:
        bucket = self.hashes.setdefault(name, {})
        is_new = key not in bucket
        bucket[key] = value
        return 1 if is_new else 0

    async def hget(self, name: str, key: str) -> str | None:
        return self.hashes.get(name, {}).get(key)

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self.hashes.get(name, {}))


@pytest.mark.asyncio
async def test_online_jwt_users_collector_uses_redis_hll_for_shared_count() -> None:
    redis = _FakeRedis()
    worker_a = OnlineJwtUsersCollector(redis_client=redis)
    worker_b = OnlineJwtUsersCollector(redis_client=redis)

    await worker_a.observe_user("user-a")
    await worker_a.observe_user("user-a")
    await worker_b.observe_user("user-a")
    await worker_b.observe_user("user-b")

    assert await worker_a.count() == 2
    assert await worker_b.count() == 2
    assert redis.pfadd_calls == 4


@pytest.mark.asyncio
async def test_online_jwt_users_collector_uses_rolling_hourly_window() -> None:
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    def current_time() -> datetime:
        return now

    redis = _FakeRedis()
    collector = OnlineJwtUsersCollector(
        redis_client=redis,
        now_factory=current_time,
    )

    await collector.observe_user("older-user")
    now += timedelta(minutes=61)
    await collector.observe_user("recent-user")

    assert await collector.hourly_count() == 1
    assert await collector.daily_count() == 2


@pytest.mark.asyncio
async def test_online_jwt_users_collector_returns_daily_user_details() -> None:
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    def current_time() -> datetime:
        return now

    collector = OnlineJwtUsersCollector(now_factory=current_time)

    await collector.observe_user("user-a", email="a@example.com", name="User A")
    now += timedelta(minutes=5)
    await collector.observe_user("user-a")
    now += timedelta(seconds=1)
    await collector.observe_user("user-b", email="b@example.com", name="User B")

    details = await collector.daily_users()

    assert [detail.id for detail in details] == ["user-b", "user-a"]
    assert details[1].email == "a@example.com"
    assert details[1].name == "User A"
    assert details[1].first_seen_at == "2026-07-02T12:00:00+00:00"
    assert details[1].last_seen_at == "2026-07-02T12:05:00+00:00"
