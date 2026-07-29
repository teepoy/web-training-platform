"""Shared sparse dataset contracts — domain models, reader, and payload store.

These types are the transport boundary between API and worker: both sides
can import from ``app.modules.storage.domain.sparse`` without pulling in
``apps.api`` internals.
"""

from app.modules.storage.domain.sparse.annotations import (
    SparseAnnotationRecord,
    SparseAnnotationStore,
    build_annotation_record,
)
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
from app.modules.storage.domain.sparse.reader import SparseManifestReader
from app.modules.storage.domain.sparse.store import DatasetPayloadStore

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
