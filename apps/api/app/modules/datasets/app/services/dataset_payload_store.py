"""Backward-compatible re-exports — canonical definitions live in ``platform_runtime.sparse.store``."""

from platform_runtime.sparse.store import (
    DatasetPayloadStore,  # noqa: F401 — re-exported for backward compat
)

__all__ = ["DatasetPayloadStore"]
