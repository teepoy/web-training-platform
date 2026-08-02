"""Regression tests for versioned SC image resolution."""

from __future__ import annotations

import hashlib
import io
from unittest.mock import AsyncMock, MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.domain.image_fetcher import ScImageFetcher
from app.modules.sc.port.http.deps import (
    get_dataset_payload_store,
    get_image_fetcher,
)
from app.modules.sc.schema import (
    _build_v2_pyarrow_schema,
    _build_v3_pyarrow_schema,
)
from app.modules.storage.adapter.sparse.storage import SparseDatasetStorage
from app.modules.storage.domain.sparse import (
    DatasetManifest,
    DatasetPayloadStore,
    SampleLocator,
    ShardEntry,
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


def _payload_store_for_row(
    row: dict[str, object],
    *,
    schema: pa.Schema,
    schema_version: str,
) -> MagicMock:
    shard_buffer = io.BytesIO()
    table = pa.Table.from_pylist([row], schema=schema)
    pq.write_table(table, shard_buffer)
    shard_bytes = shard_buffer.getvalue()

    shard = ShardEntry(
        shard_index=0,
        uri="shards/shard-0.parquet",
        row_count=1,
        byte_size=len(shard_bytes),
        checksum_sha256=hashlib.sha256(shard_bytes).hexdigest(),
    )
    locator = SampleLocator(dataset_id="test-ds", shard_index=0, row_index=0)
    manifest = DatasetManifest(
        dataset_id="test-ds",
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=1,
        shards=[shard],
        sample_index={"42": locator},
        schema_version=schema_version,
    )

    artifact_storage = MagicMock()
    artifact_storage.get_bytes = AsyncMock(return_value=shard_bytes)
    payload_store = MagicMock(spec=DatasetPayloadStore)
    payload_store.storage = artifact_storage
    payload_store.get_manifest = AsyncMock(return_value=manifest)
    payload_store.lookup_sample_locators = AsyncMock(return_value={"42": locator})
    return payload_store


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
        "/api/v1/sc/datasets/test-ds/samples/42/images/1"
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
        "/api/v1/sc/datasets/test-ds/samples/42/images/42_template"
    )


def test_v2_image_proxy_uses_persisted_review_locator() -> None:
    payload_store = _payload_store_for_row(
        _v2_row(),
        schema=_build_v2_pyarrow_schema(),
        schema_version="v2",
    )
    fetcher = AsyncMock(spec=ScImageFetcher)
    fetcher.get_image_bytes = AsyncMock(return_value=b"v2-review")

    app.dependency_overrides[get_dataset_payload_store] = lambda: payload_store
    app.dependency_overrides[get_image_fetcher] = lambda: fetcher
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/sc/datasets/test-ds/samples/42/images/1"
            )
    finally:
        app.dependency_overrides.pop(get_dataset_payload_store, None)
        app.dependency_overrides.pop(get_image_fetcher, None)

    assert response.status_code == 200, response.text
    assert response.content == b"v2-review"
    fetcher.get_image_bytes.assert_awaited_once_with(
        inspection_time="2026-05-26T08:00:00+00:00",
        wafer_key=1,
        defect_id="42",
        image_type="review",
        review_image_id=5,
    )


@pytest.mark.parametrize(
    ("image_id", "image_type", "review_image_id", "content_type"),
    [
        ("42_template", "template", None, "image/png"),
        ("9", "review", 9, "image/jpeg"),
    ],
)
def test_v3_image_proxy_derives_locator_from_scalar_identity(
    image_id: str,
    image_type: str,
    review_image_id: int | None,
    content_type: str,
) -> None:
    payload_store = _payload_store_for_row(
        _v3_row(),
        schema=_build_v3_pyarrow_schema(),
        schema_version="v3",
    )
    fetcher = AsyncMock(spec=ScImageFetcher)
    fetcher.get_image_bytes = AsyncMock(return_value=b"v3-image")

    app.dependency_overrides[get_dataset_payload_store] = lambda: payload_store
    app.dependency_overrides[get_image_fetcher] = lambda: fetcher
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/sc/datasets/test-ds/samples/42/images/{image_id}"
            )
    finally:
        app.dependency_overrides.pop(get_dataset_payload_store, None)
        app.dependency_overrides.pop(get_image_fetcher, None)

    assert response.status_code == 200, response.text
    assert response.content == b"v3-image"
    assert response.headers["content-type"] == content_type
    fetcher.get_image_bytes.assert_awaited_once_with(
        inspection_time="2026-05-26T08:00:00+00:00",
        wafer_key=1,
        defect_id="42",
        image_type=image_type,
        review_image_id=review_image_id,
    )
