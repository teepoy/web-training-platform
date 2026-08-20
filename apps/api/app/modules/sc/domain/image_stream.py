from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class ScImageStreamSession(Protocol):
    async def resolve_images(
        self,
        *,
        roles: Sequence[str],
        items: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]: ...


class ScPredictionImageStreamFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[ScImageStreamSession]: ...


class ScTrainingImageStreamFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[ScImageStreamSession]: ...


class ScExportImageStreamFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[ScImageStreamSession]: ...


__all__ = [
    "ScExportImageStreamFactory",
    "ScImageStreamSession",
    "ScPredictionImageStreamFactory",
    "ScTrainingImageStreamFactory",
]
