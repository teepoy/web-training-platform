from __future__ import annotations

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
    assert redis.pfadd_calls == 3
