"""SC sparse schema compatibility tests.

New imports use the identity-only v4 schema. The v2/v3 contracts remain
supported for compatibility identity projection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pyarrow as pa
import pytest

from app.modules.sc.app.services.sc_import_service import _transform_upstream_batch
from app.modules.sc.schema import (
    SC_IMAGE_STRUCT_DTYPE,
    SC_SOURCE_SCHEMA_VERSION,
    SC_SPARSE_SHARD_SCHEMA_V2,
    SC_SPARSE_SHARD_SCHEMA_V3,
    SC_SPARSE_SHARD_SCHEMA_V4,
    _build_v2_pyarrow_schema,
    _build_v3_pyarrow_schema,
    _build_v4_pyarrow_schema,
    check_sc_v2_or_raise,
    find_images_by_role,
)


def test_v2_schema_retains_embedded_image_contract() -> None:
    schema = _build_v2_pyarrow_schema()

    assert isinstance(SC_IMAGE_STRUCT_DTYPE, pa.StructType)
    assert schema.names == [column["name"] for column in SC_SPARSE_SHARD_SCHEMA_V2]
    assert isinstance(schema.field("images").type, pa.ListType)
    assert isinstance(schema.field("images").type.value_type, pa.StructType)
    assert schema.field("images").type.value_type == SC_IMAGE_STRUCT_DTYPE


def test_v2_schema_round_trips_existing_image_rows() -> None:
    image = {
        "image_id": "42_template",
        "image_type": "template",
        "role": "patch_template",
        "content_type": "image/png",
        "filename": "template.png",
        "bytes": None,
        "review_image_id": None,
        "source_uri": "mock-sc://patch/42/template.png",
    }
    row = {
        "sample_id": "42",
        "defect_id": "42",
        "inspection_time": "2026-05-26T08:00:00+00:00",
        "wafer_key": 1,
        "wafer_x": 100,
        "wafer_y": 200,
        "die_x": 0,
        "die_y": 0,
        "rough_bin": 1,
        "class_number": 2,
        "test_id": 7,
        "lot_id": "LOT-2026-001",
        "has_review": 0,
        "images": [image],
    }

    restored = pa.Table.from_pylist(
        [row], schema=_build_v2_pyarrow_schema()
    ).to_pylist()[0]

    assert restored["images"] == [image]
    assert find_images_by_role(restored["images"], "patch_template") == [image]


def test_v3_schema_remains_available_for_compatibility() -> None:
    schema = _build_v3_pyarrow_schema()

    assert schema.names == [column["name"] for column in SC_SPARSE_SHARD_SCHEMA_V3]
    assert "images" not in schema.names
    assert "image_uris" not in schema.names
    assert "metadata" not in schema.names


def test_v4_schema_is_identity_only() -> None:
    schema = _build_v4_pyarrow_schema()

    assert SC_SOURCE_SCHEMA_VERSION == "v4_identity"
    assert schema.names == [column["name"] for column in SC_SPARSE_SHARD_SCHEMA_V4]
    assert schema.names == ["sample_id", "defect_id"]


def test_transform_upstream_batch_generates_unique_opaque_platform_sample_ids() -> None:
    batch = pa.RecordBatch.from_pylist(
        [
            {
                "defect_id": 42,
                "wafer_x": 100,
                "wafer_y": 200,
                "die_x": 1,
                "die_y": 2,
                "rough_bin": 3,
                "class_number": 4,
                "test_id": 5,
                "lot_id": "LOT-1",
                "index_x": 17,
                "cluster": 9,
                "images": 6,
                "future_metric": 12.5,
            },
            {
                "defect_id": 43,
                "wafer_x": 101,
                "wafer_y": 201,
                "die_x": 2,
                "die_y": 3,
                "rough_bin": 4,
                "class_number": 5,
                "test_id": 6,
                "lot_id": "LOT-1",
            },
        ]
    )

    table = _transform_upstream_batch(
        batch,
        inspection_time=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        wafer_key=1,
    )

    assert table.column_names == ["sample_id", "defect_id"]
    rows = table.to_pylist()
    assert [row["defect_id"] for row in rows] == ["42", "43"]
    sample_ids = [str(row["sample_id"]) for row in rows]
    assert len(set(sample_ids)) == 2
    assert set(sample_ids).isdisjoint({"42", "43"})
    assert all(UUID(sample_id).version == 4 for sample_id in sample_ids)


def test_transform_upstream_batch_ignores_compatible_extra_field_changes() -> None:
    first = pa.RecordBatch.from_pylist(
        [
            {
                "defect_id": 1,
                "wafer_x": 1,
                "wafer_y": 2,
                "die_x": 3,
                "die_y": 4,
                "rough_bin": 5,
                "future_metric": 1.5,
            }
        ]
    )
    first_table = _transform_upstream_batch(
        first,
        inspection_time=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        wafer_key=1,
    )
    changed = pa.RecordBatch.from_pylist(
        [
            {
                "defect_id": 2,
                "wafer_x": 1,
                "wafer_y": 2,
                "die_x": 3,
                "die_y": 4,
                "rough_bin": 5,
                "replacement_metric": 2.5,
            }
        ]
    )

    table = _transform_upstream_batch(
        changed,
        inspection_time=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        wafer_key=1,
        schema=first_table.schema,
    )

    row = table.to_pylist()[0]
    assert row["defect_id"] == "2"
    assert UUID(str(row["sample_id"])).version == 4


def test_find_images_by_role_remains_available_for_v2_readers() -> None:
    images: list[dict[str, object]] = [
        {"image_id": "1", "role": "review"},
        {"image_id": "2", "role": "patch_template"},
    ]

    assert find_images_by_role(images, "review") == [images[0]]
    assert find_images_by_role(images, "missing") == []


def test_check_sc_v2_or_raise_remains_pinned_to_v2() -> None:
    manifest = MagicMock(schema_version="v2")
    check_sc_v2_or_raise(manifest)

    manifest.schema_version = "v3"
    with pytest.raises(ValueError, match="expected 'v2'"):
        check_sc_v2_or_raise(manifest)
