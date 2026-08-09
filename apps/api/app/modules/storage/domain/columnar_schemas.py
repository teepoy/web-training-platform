"""Canonical Arrow schemas for storage-owned columnar artifacts.

These schemas describe physical Parquet formats whose writers and readers live
inside the storage module.  Versioned runtime view schemas remain in
``storage.domain.data_plane.schemas`` because they are cross-process contracts,
not storage implementation details.
"""

from __future__ import annotations

import pyarrow as pa

SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE = pa.struct(
    [
        pa.field("image_id", pa.string(), nullable=False),
        pa.field("image_type", pa.string(), nullable=False),
        pa.field("role", pa.string(), nullable=False),
        pa.field("content_type", pa.string(), nullable=False),
        pa.field("filename", pa.string(), nullable=False),
        pa.field("bytes", pa.binary(), nullable=True),
        pa.field("review_image_id", pa.int32(), nullable=True),
        pa.field("source_uri", pa.string(), nullable=True),
    ]
)

SPARSE_INDEX_SAMPLE_ID_COLUMN = "sample_id"
SPARSE_INDEX_SHARD_COLUMN = "shard_index"
SPARSE_INDEX_ROW_COLUMN = "row_index"
SPARSE_INDEX_UPSTREAM_ID_COLUMN = "upstream_item_id"
SPARSE_INDEX_SCHEMA = pa.schema(
    [
        pa.field(SPARSE_INDEX_SAMPLE_ID_COLUMN, pa.string(), nullable=False),
        pa.field(SPARSE_INDEX_SHARD_COLUMN, pa.int32(), nullable=False),
        pa.field(SPARSE_INDEX_ROW_COLUMN, pa.int32(), nullable=False),
        pa.field(SPARSE_INDEX_UPSTREAM_ID_COLUMN, pa.string(), nullable=True),
    ]
)
SPARSE_INDEX_COLUMNS = tuple(SPARSE_INDEX_SCHEMA.names)

SPARSE_PREDICTION_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("predicted_label", pa.string(), nullable=False),
        pa.field("confidence", pa.float64(), nullable=True),
        pa.field("all_scores", pa.string(), nullable=True),
        pa.field("model_id", pa.string(), nullable=False),
        pa.field("target", pa.string(), nullable=True),
        pa.field("model_version", pa.string(), nullable=True),
        pa.field("job_id", pa.string(), nullable=False),
        pa.field("error", pa.string(), nullable=True),
    ]
)
SPARSE_PREDICTION_COLUMNS = tuple(SPARSE_PREDICTION_SCHEMA.names)

DB_FULL_MATERIALIZED_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_uris", pa.list_(pa.string()), nullable=False),
        pa.field("metadata", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
    ]
)

SPARSE_MATERIALIZED_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
    ]
)

__all__ = [
    "DB_FULL_MATERIALIZED_SCHEMA",
    "SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE",
    "SPARSE_INDEX_COLUMNS",
    "SPARSE_INDEX_ROW_COLUMN",
    "SPARSE_INDEX_SAMPLE_ID_COLUMN",
    "SPARSE_INDEX_SCHEMA",
    "SPARSE_INDEX_SHARD_COLUMN",
    "SPARSE_INDEX_UPSTREAM_ID_COLUMN",
    "SPARSE_MATERIALIZED_SCHEMA",
    "SPARSE_PREDICTION_COLUMNS",
    "SPARSE_PREDICTION_SCHEMA",
]
