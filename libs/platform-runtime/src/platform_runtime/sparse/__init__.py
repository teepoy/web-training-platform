"""Shared sparse dataset contracts — domain models, reader, and payload store.

These types are the transport boundary between API and worker: both sides
can import from ``platform_runtime.sparse`` without pulling in
``apps.api`` internals.
"""

from platform_runtime.sparse.annotations import (
    SparseAnnotationRecord,
    SparseAnnotationStore,
    build_annotation_record,
)
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
from platform_runtime.sparse.reader import SparseManifestReader
from platform_runtime.sparse.store import DatasetPayloadStore

__all__ = [
    "ColumnSchema",
    "DatasetManifest",
    "DatasetPayloadStore",
    "SampleLocator",
    "ShardEntry",
    "SparseAnnotationRecord",
    "SparseAnnotationStore",
    "SparseManifestReader",
    "SparsePredictionJobResult",
    "SparsePredictionResult",
    "SparsePredictionShard",
    "SparseRowIdentity",
    "build_annotation_record",
]
