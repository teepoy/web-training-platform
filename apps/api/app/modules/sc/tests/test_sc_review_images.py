"""Regression tests for SC review image handling.

Verifies that review images survive the full chain:
import → Parquet write → Parquet read → _normalize_v2_row → view mapper.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.models import PatchSample, ReviewImage
from app.modules.sc.app.services.sc_import_service import (
    _build_image_structs,
    _patch_sample_to_parquet_row,
)

INSP_DT = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)

MOCK_REVIEW_URI_TPL = (
    "mock-sc://review/2026-05-26T08:00:00+00:00/1/{defect_id}"
)


def _make_review_image(
    image_url: str, image_id: int = 1, image_type: str = "REVIEW_HIGH_MAG"
) -> ReviewImage:
    return ReviewImage(
        image_url=image_url,
        image_name=image_url.split("/")[-1] + ".png",
        image_id=image_id,
        image_type=image_type,
    )


def _sample_with_review_images(
    defect_id: str, review_count: int = 2
) -> PatchSample:
    review_images = [
        _make_review_image(
            MOCK_REVIEW_URI_TPL.format(defect_id=defect_id) + f"/{i}",
            image_id=i,
        )
        for i in range(1, review_count + 1)
    ]
    return PatchSample(
        sample_id=defect_id,
        defect_id=defect_id,
        wafer_key=1,
        lot_id="LOT-2026-001",
        wafer_x=100,
        wafer_y=200,
        rough_bin=1,
        class_number=2,
        inspection_time=INSP_DT,
        review_images=review_images,
    )


# ── _build_image_structs tests ──────────────────────────────────────────


class TestBuildImageStructsReviewMetadata:
    def test_review_images_have_correct_image_type_and_review_image_id(self) -> None:
        ps = _sample_with_review_images("42", review_count=2)
        images = asyncio.run(
            _build_image_structs(
                patch_sample=ps,
                inspection_time=INSP_DT,
                wafer_key=1,
            )
        )

        assert len(images) == 5  # 2 review + template + defective + difference

        review_imgs = [img for img in images if img["role"] == "review"]
        assert len(review_imgs) == 2

        for i, rimg in enumerate(review_imgs):
            assert rimg["image_type"] == "review", (
                f"review[{i}] image_type expected 'review', got {rimg['image_type']!r}"
            )
            assert rimg["review_image_id"] == i + 1, (
                f"review[{i}] review_image_id expected {i+1}, got {rimg['review_image_id']!r}"
            )
            assert rimg["bytes"] is None, "bytes should be None (lazy fetch)"
            assert rimg["role"] == "review"

        patch_imgs = [img for img in images if img["role"] != "review"]
        for pimg in patch_imgs:
            assert pimg["review_image_id"] is None, (
                f"patch image {pimg['role']} should have review_image_id=None"
            )
            assert pimg["bytes"] is None


# ── Full round-trip tests ───────────────────────────────────────────────


class TestReviewImageRoundTrip:
    def test_parquet_roundtrip_preserves_image_type_and_review_image_id(
        self,
    ) -> None:
        from app.modules.sc.schema import _build_v2_pyarrow_schema

        ps = _sample_with_review_images("42", review_count=2)
        images = asyncio.run(
            _build_image_structs(
                patch_sample=ps,
                inspection_time=INSP_DT,
                wafer_key=1,
            )
        )

        row = _patch_sample_to_parquet_row(ps, images)
        table = pa.Table.from_pylist([row], schema=_build_v2_pyarrow_schema())

        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)

        restored = pq.read_table(buf).to_pylist()[0]
        restored_images: list[dict[str, object]] = []
        raw = restored.get("images")
        if isinstance(raw, list):
            restored_images = [dict(cast(dict[str, object], img)) for img in raw]

        assert len(restored_images) == 5

        # Check review images preserved
        review_imgs = [img for img in restored_images if img.get("role") == "review"]
        assert len(review_imgs) == 2
        assert review_imgs[0]["image_id"] == "1"
        assert review_imgs[0]["image_type"] == "review"
        assert review_imgs[0]["review_image_id"] == 1
        assert review_imgs[1]["image_id"] == "2"
        assert review_imgs[1]["review_image_id"] == 2

        # Check patch images
        patch_imgs = [img for img in restored_images if img.get("role") != "review"]
        assert len(patch_imgs) == 3
        for pimg in patch_imgs:
            assert pimg["review_image_id"] is None

    def test_normalize_v2_row_populates_image_type_and_review_image_id(
        self,
    ) -> None:
        from app.modules.storage.adapter.sparse.storage import SparseDatasetStorage
        from app.modules.storage.domain.sparse import DatasetPayloadStore

        mock_storage = MagicMock()
        mock_payload_store = MagicMock(spec=DatasetPayloadStore)

        store = SparseDatasetStorage(
            dataset_id="test-ds",
            org_id="test-org",
            storage=mock_storage,
            payload_store=mock_payload_store,
            session_factory=MagicMock(),
            repo=MagicMock(),
            dataset_type="image_sc",
        )

        row: dict[str, object] = {
            "sample_id": "42",
            "defect_id": "42",
            "inspection_time": "2026-05-26T08:00:00+00:00",
            "wafer_key": 1,
            "images": [
                {
                    "image_id": "1",
                    "image_type": "review",
                    "role": "review",
                    "content_type": "image/jpeg",
                    "filename": "review_1.jpg",
                    "bytes": None,
                    "review_image_id": 1,
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

        sr = store._normalize_v2_row(row, "42")

        assert sr.images is not None
        assert len(sr.images) == 2

        review_ref = sr.images[0]
        assert review_ref.role == "review"
        assert review_ref.image_type == "review"
        assert review_ref.review_image_id == 1
        assert review_ref.access_url.startswith("/api/v1/sc/datasets/test-ds/samples/42/images/")

        patch_ref = sr.images[1]
        assert patch_ref.role == "patch_template"
        assert patch_ref.image_type == "template"
        assert patch_ref.review_image_id is None

    def test_mapper_populates_image_type_correctly(self) -> None:
        from app.modules.datasets.domain.mapper import (
            _embedded_bytes_to_sc_image_refs,
        )
        from app.modules.datasets.domain.sample_row import (
            SampleRow,
            SampleRowImageRef,
        )

        row = SampleRow(
            sample_id="42",
            dataset_id="test-ds",
            images=[
                SampleRowImageRef(
                    image_id="1",
                    role="review",
                    content_type="image/jpeg",
                    filename="review_1.jpg",
                    image_type="review",
                    review_image_id=1,
                ),
                SampleRowImageRef(
                    image_id="42_template",
                    role="patch_template",
                    content_type="image/png",
                    filename="template.png",
                    image_type="template",
                    review_image_id=None,
                ),
            ],
        )

        refs = _embedded_bytes_to_sc_image_refs(row, dataset_id="test-ds")

        assert len(refs) == 2
        assert refs[0].role == "review"
        assert refs[0].image_type == "review", (
            f"expected 'review', got {refs[0].image_type!r}"
        )
        assert refs[0].image_id == "1"

        assert refs[1].role == "patch_template"
        assert refs[1].image_type == "template", (
            f"expected 'template', got {refs[1].image_type!r}"
        )

    def test_patch_image_v1_view_includes_review_images(self) -> None:
        from app.modules.datasets.domain.mapper import (
            sample_row_to_sc_patch_image_v1,
        )
        from app.modules.datasets.domain.sample_row import (
            SampleRow,
            SampleRowImageRef,
        )
        from app.modules.datasets.domain.view_projection import (
            ViewProjectionContext,
        )

        row = SampleRow(
            sample_id="42",
            dataset_id="test-ds",
            metadata={
                "inspection_time": "2026-05-26T08:00:00+00:00",
                "wafer_key": 1,
                "defect_id": "42",
                "wafer_x": 100,
                "wafer_y": 200,
                "rough_bin": 1,
                "sample_id": "42",
            },
            images=[
                SampleRowImageRef(
                    image_id="1",
                    role="review",
                    content_type="image/jpeg",
                    filename="review_1.jpg",
                    image_type="review",
                    review_image_id=1,
                ),
                SampleRowImageRef(
                    image_id="2",
                    role="review",
                    content_type="image/jpeg",
                    filename="review_2.jpg",
                    image_type="review",
                    review_image_id=2,
                ),
                SampleRowImageRef(
                    image_id="42_template",
                    role="patch_template",
                    content_type="image/png",
                    filename="template.png",
                    image_type="template",
                ),
            ],
        )

        view_row = sample_row_to_sc_patch_image_v1(
            row,
            context=ViewProjectionContext(
                dataset_id="test-ds",
                dataset_type="image_sc",
            ),
        )

        assert len(view_row.images) == 3
        assert len(view_row.review_images) == 2
        assert view_row.review_images[0] == {"image_id": "1"}
        assert view_row.review_images[1] == {"image_id": "2"}


# ── SC image serving endpoint tests ─────────────────────────────────────


class TestScImageServingLazyFetchReview:
    def test_lazy_fetch_review_image_passes_review_image_id(self) -> None:
        import pyarrow.parquet as pq

        from app.modules.storage.domain.sparse import DatasetManifest, DatasetPayloadStore, SampleLocator, ShardEntry
        from app.modules.sc.schema import _build_v2_pyarrow_schema
        from app.modules.sc.port.http.deps import (
            get_dataset_payload_store,
            get_image_fetcher,
        )
        from app.modules.sc.domain.image_fetcher import ScImageFetcher

        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

        mock_fetcher = AsyncMock(spec=ScImageFetcher)
        mock_fetcher.get_image_bytes = AsyncMock(return_value=fake_image_bytes)

        ds_id = "ds-review-test"
        sample_id = "42"
        image_id = "1"

        # Write a parquet shard with a review image (bytes=None, review_image_id=5)
        shard_buf = io.BytesIO()
        table = pa.Table.from_pylist(
            [
                {
                    "sample_id": sample_id,
                    "defect_id": "42",
                    "inspection_time": "2026-05-26T08:00:00+00:00",
                    "wafer_key": 1,
                    "wafer_x": 100,
                    "wafer_y": 200,
                    "die_x": 0,
                    "die_y": 0,
                    "rough_bin": 1,
                    "class_number": 1,
                    "lot_id": "LOT001",
                    "images": [
                        {
                            "image_id": image_id,
                            "image_type": "review",
                            "role": "review",
                            "content_type": "image/jpeg",
                            "filename": "review_1.jpg",
                            "bytes": None,
                            "review_image_id": 5,
                            "source_uri": None,
                        }
                    ],
                }
            ],
            schema=_build_v2_pyarrow_schema(),
        )
        pq.write_table(table, shard_buf)
        shard_buf.seek(0)
        shard_bytes = shard_buf.read()

        mock_storage = MagicMock()
        mock_storage.get_bytes = AsyncMock(return_value=shard_bytes)

        import hashlib

        shard_entry = ShardEntry(
            shard_index=0,
            uri="shards/shard-0.parquet",
            row_count=1,
            byte_size=len(shard_bytes),
            checksum_sha256=hashlib.sha256(shard_bytes).hexdigest(),
        )
        locator = SampleLocator(
            dataset_id=ds_id,
            shard_index=0,
            row_index=0,
        )
        manifest = DatasetManifest(
            dataset_id=ds_id,
            storage_mode="file_shard_sparse",
            shard_count=1,
            total_rows=1,
            shards=[shard_entry],
            sample_index={sample_id: locator},
            schema_version="v2",
        )

        mock_payload_store = MagicMock(spec=DatasetPayloadStore)
        mock_payload_store.get_manifest = AsyncMock(return_value=manifest)
        mock_payload_store._storage = mock_storage

        app.dependency_overrides[get_dataset_payload_store] = lambda: mock_payload_store
        app.dependency_overrides[get_image_fetcher] = lambda: mock_fetcher
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/api/v1/sc/datasets/{ds_id}/samples/{sample_id}/images/{image_id}",
                )
                assert resp.status_code == 200, resp.text
                assert resp.content == fake_image_bytes
                assert resp.headers["content-type"] == "image/jpeg"

                mock_fetcher.get_image_bytes.assert_awaited_once()
                call_kwargs = mock_fetcher.get_image_bytes.call_args.kwargs
                assert call_kwargs["inspection_time"] == "2026-05-26T08:00:00+00:00"
                assert call_kwargs["wafer_key"] == 1
                assert call_kwargs["defect_id"] == "42"
                assert call_kwargs["image_type"] == "review"
                assert call_kwargs["review_image_id"] == 5
        finally:
            app.dependency_overrides.pop(get_dataset_payload_store, None)
            app.dependency_overrides.pop(get_image_fetcher, None)
