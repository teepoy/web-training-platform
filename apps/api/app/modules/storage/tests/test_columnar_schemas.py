from __future__ import annotations

import pyarrow as pa

from app.modules.sc.schema import SC_IMAGE_STRUCT_DTYPE
from app.modules.storage.domain.columnar_schemas import (
    DB_FULL_MATERIALIZED_SCHEMA,
    SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE,
    SPARSE_INDEX_SCHEMA,
    SPARSE_MATERIALIZED_SCHEMA,
    SPARSE_PREDICTION_SCHEMA,
)


def test_sc_and_generic_sparse_writers_share_image_struct() -> None:
    assert SC_IMAGE_STRUCT_DTYPE.equals(SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE)
    assert SPARSE_EMBEDDED_IMAGE_STRUCT_DTYPE.field("review_image_id").type == pa.int32()


def test_sparse_index_empty_table_preserves_physical_schema() -> None:
    table = pa.Table.from_pylist([], schema=SPARSE_INDEX_SCHEMA)

    assert table.schema.equals(SPARSE_INDEX_SCHEMA)


def test_prediction_nullable_values_keep_declared_arrow_types() -> None:
    table = pa.Table.from_pylist(
        [
            {
                "sample_id": "sample-1",
                "predicted_label": "scratch",
                "model_id": "model-1",
                "job_id": "job-1",
            }
        ],
        schema=SPARSE_PREDICTION_SCHEMA,
    )

    assert table.schema.equals(SPARSE_PREDICTION_SCHEMA)
    assert table.schema.field("confidence").type == pa.float64()
    assert table.schema.field("all_scores").type == pa.string()
    assert table["confidence"].to_pylist() == [None]


def test_sparse_materialization_keeps_late_optional_image_column() -> None:
    table = pa.Table.from_pylist(
        [
            {"sample_id": "sample-1"},
            {"sample_id": "sample-2", "image_bytes": b"image"},
        ],
        schema=SPARSE_MATERIALIZED_SCHEMA,
    )

    assert table.schema.equals(SPARSE_MATERIALIZED_SCHEMA)
    assert table["image_bytes"].to_pylist() == [None, b"image"]


def test_db_full_empty_materialization_has_complete_schema() -> None:
    table = pa.Table.from_pylist([], schema=DB_FULL_MATERIALIZED_SCHEMA)

    assert table.schema.equals(DB_FULL_MATERIALIZED_SCHEMA)
    assert table.column_names == [
        "sample_id",
        "image_uris",
        "metadata",
        "image_bytes",
    ]
