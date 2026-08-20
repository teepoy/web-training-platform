"""Regression tests for versioned SC image resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pyarrow as pa

from app.modules.sc.schema import (
    _build_v2_pyarrow_schema,
    _build_v3_pyarrow_schema,
)
from app.modules.storage.adapter.sparse.storage import SparseDatasetStorage
from app.modules.storage.domain.sparse import (
    DatasetPayloadStore,
)


def _v2_row() -> dict[str, object]:
    return {
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
        "lot_id": "LOT-1",
        "has_review": 1,
        "images": [
            {
                "image_id": "1",
                "image_type": "review",
                "role": "review",
                "content_type": "image/jpeg",
                "filename": "review_1.jpg",
                "bytes": None,
                "review_image_id": 5,
                "source_uri": None,
            },
            {
                "image_id": "42_template",
                "image_type": "template",
                "role": "patch_template",
                "content_type": "image/png",
                "filename": "template.png",
                "bytes": None,
                "review_image_id": None,
                "source_uri": None,
            },
        ],
    }


def _v3_row() -> dict[str, object]:
    row = dict(_v2_row())
    row.pop("images")
    return row


def _sparse_storage() -> SparseDatasetStorage:
    return SparseDatasetStorage(
        dataset_id="test-ds",
        org_id="test-org",
        dataset_metadata=MagicMock(),
        storage=MagicMock(),
        payload_store=MagicMock(spec=DatasetPayloadStore),
        session_factory=MagicMock(),
        repo=MagicMock(),
        prediction_compaction_memory_limit="64MiB",
        prediction_compaction_temp_limit="256MiB",
        prediction_compaction_row_group_rows=1_000,
        dataset_type="image_sc",
    )


def test_v2_reader_keeps_existing_review_image_locator() -> None:
    row = _v2_row()
    restored = pa.Table.from_pylist(
        [row], schema=_build_v2_pyarrow_schema()
    ).to_pylist()[0]

    sample = _sparse_storage()._row_to_sample_row(restored, schema_version="v2")

    assert sample.images is not None
    assert sample.images[0].image_type == "review"
    assert sample.images[0].review_image_id == 5
    assert sample.images[0].access_url == (
        "/api/v1/sc/images/2026-05-26T08%3A00%3A00%2B00%3A00/1/42/"
        "review?review_image_id=5"
    )


def test_v3_reader_uses_scalar_metadata_without_image_refs() -> None:
    row = _v3_row()
    restored = pa.Table.from_pylist(
        [row], schema=_build_v3_pyarrow_schema()
    ).to_pylist()[0]

    sample = _sparse_storage()._row_to_sample_row(restored, schema_version="v3")

    assert sample.images is None
    assert sample.image_uris == []
    assert sample.metadata["defect_id"] == "42"
    assert sample.metadata["inspection_time"] == "2026-05-26T08:00:00+00:00"


def test_v3_patch_view_derives_refs_only_during_projection() -> None:
    from app.modules.datasets.domain.mapper import sample_row_to_sc_patch_image_v1
    from app.modules.datasets.domain.view_projection import ViewProjectionContext

    sample = _sparse_storage()._row_to_sample_row(_v3_row(), schema_version="v3")

    view_row = sample_row_to_sc_patch_image_v1(
        sample,
        context=ViewProjectionContext(
            dataset_id="test-ds",
            dataset_type="image_sc",
        ),
    )

    assert sample.images is None
    assert [image.role for image in view_row.images] == [
        "patch_template",
        "patch_defective",
        "patch_difference",
    ]
    assert view_row.images[0].url == (
        "/api/v1/sc/images/2026-05-26T08%3A00%3A00%2B00%3A00/1/42/template"
    )
