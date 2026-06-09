"""Backward-compatible re-exports — canonical definitions live in ``platform_runtime.sparse.models``."""

from platform_runtime.sparse.models import (
    ColumnSchema,
    DatasetManifest,
    SampleLocator,
    ShardEntry,
    SparsePredictionJobResult,
    SparsePredictionResult,
    SparsePredictionShard,
    SparseRowIdentity,
)

__all__ = [
    "ColumnSchema",
    "DatasetManifest",
    "SampleLocator",
    "ShardEntry",
    "SparsePredictionJobResult",
    "SparsePredictionResult",
    "SparsePredictionShard",
    "SparseRowIdentity",
]
