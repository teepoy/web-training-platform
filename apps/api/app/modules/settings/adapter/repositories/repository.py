from __future__ import annotations

from typing import Any


class InMemorySettingsRepository:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> bool:
        if key not in self._store:
            return False
        del self._store[key]
        return True

    async def list_all(self) -> dict[str, Any]:
        return dict(self._store)
