from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class ScPatchImageBatchResolver(Protocol):
    def resolve_patch_images(
        self,
        *,
        source_profile: str,
        roles: list[str],
        items: list[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]: ...


class ScTrainingImageSourceFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[ScPatchImageBatchResolver]: ...


__all__ = ["ScPatchImageBatchResolver", "ScTrainingImageSourceFactory"]
