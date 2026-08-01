from __future__ import annotations

from typing import Protocol

from app.modules.sc.data_provider.scope import ScDataScope


class RevisionRedis(Protocol):
    async def get(self, name: str) -> bytes | str | None: ...

    async def incr(self, name: str) -> int: ...

    async def set(self, name: str, value: str, *, nx: bool = False) -> object: ...


class ScDataRevisionStore:
    def __init__(self, redis: RevisionRedis, *, namespace: str) -> None:
        self._redis = redis
        self._namespace = namespace

    def key(self, scope: ScDataScope) -> str:
        return f"{self._namespace}:revision:{scope.public_name}"

    async def current(self, scope: ScDataScope) -> int:
        key = self.key(scope)
        value = await self._redis.get(key)
        if value is None:
            await self._redis.set(key, "0", nx=True)
            value = await self._redis.get(key)
        if value is None:
            raise RuntimeError(f"failed to initialize revision for {scope.public_name}")
        return int(value)

    async def increment(self, scope: ScDataScope) -> int:
        return int(await self._redis.incr(self.key(scope)))
