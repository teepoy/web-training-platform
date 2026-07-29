"""Backward-compatible re-exports — canonical definitions live in ``app.modules.storage.domain.sparse.models``."""

from app.modules.storage.domain.sparse.models import (
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
