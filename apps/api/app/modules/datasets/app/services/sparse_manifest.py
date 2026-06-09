"""Backward-compatible re-exports — canonical definitions live in ``platform_runtime.sparse.reader``."""

from platform_runtime.sparse.reader import (
    SparseManifestReader,  # noqa: F401 — re-exported for backward compat
)

__all__ = ["SparseManifestReader"]
