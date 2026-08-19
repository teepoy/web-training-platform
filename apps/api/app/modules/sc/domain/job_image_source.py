from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol


class ScPatchImageBatchResolver(Protocol):
    def resolve_patch_images(
        self,
        *,
        source_format: str,
        roles: list[str],
        items: list[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]: ...


class ScJobImageSourceFactory(Protocol):
    def open(self) -> AbstractAsyncContextManager[ScPatchImageBatchResolver]: ...


def normalize_role_paths(value: object) -> dict[str, str]:
    """Normalize an explicit role-to-relative-path mapping without inventing layout."""

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("role_paths must be a mapping of image role to relative path")
    normalized: dict[str, str] = {}
    for raw_role, raw_path in value.items():
        role = str(raw_role).strip()
        if not role:
            raise ValueError("role_paths contains an empty image role")
        if not isinstance(raw_path, str):
            raise ValueError(f"role_paths[{role!r}] must be a string")
        normalized[role] = raw_path
    return normalized


__all__ = [
    "ScJobImageSourceFactory",
    "ScPatchImageBatchResolver",
    "normalize_role_paths",
]
