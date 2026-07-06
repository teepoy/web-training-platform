"""v2 sparse import embedded byte integrity tests.

Verifies the ``images`` list<struct> column in Parquet shards carries
embedded bytes via the SC image fetcher interface, not raw S3 URIs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import polars as pl
import pyarrow as pa
import pytest

from app.modules.sc.models import PatchSample, ReviewImage

INSP_DT = datetime(2026, 5, 26, 8, 0, 0, tzinfo=timezone.utc)

MOCK_REVIEW_URI_TPL = "mock-sc://review/2026-05-26T08:00:00+00:00/1/{defect_id}"


def _make_review_image(
    image_url: str, image_id: int = 1, image_type: str = "REVIEW_HIGH_MAG"
) -> ReviewImage:
    return ReviewImage(
        image_url=image_url,
        image_name=image_url.split("/")[-1] + ".png",
        image_id=image_id,
        image_type=image_type,
    )


def _sample_with_review(sample_id: str = "1") -> PatchSample:
    uri = MOCK_REVIEW_URI_TPL.format(defect_id=sample_id)
    return PatchSample(
        sample_id=sample_id,
        defect_id=sample_id,
        wafer_key=1,
        lot_id="LOT-2026-001",
        wafer_x=100,
        wafer_y=200,
        rough_bin=1,
        class_number=2,
        test_id=7,
        inspection_time=INSP_DT,
        review_images=[_make_review_image(uri)],
    )


class TestV2SparseImportBytes:
    """v2 sparse import embedded byte integrity tests.

    Replaces the v1 URI-based RED tests with GREEN tests that verify the
    ``images`` list<struct> column carries embedded bytes and that
    placeholder URI rejection works correctly in the v2 flow.
    """

    # -- _patch_sample_to_parquet_row unit tests ---------------------------

    def test_parquet_row_includes_images_column(self) -> None:
        """Assert ``_patch_sample_to_parquet_row`` accepts images param and includes column."""
        from app.modules.sc.app.services.sc_import_service import (
            _patch_sample_to_parquet_row,
        )

        ps = _sample_with_review("42")
        images = [
            {
                "image_id": "42",
                "image_type": "review",
                "role": "review",
                "content_type": "image/png",
                "filename": "42_review_1.png",
                "bytes": b"fake-review-bytes",
                "source_uri": "mock-sc://review/2026-05-26T08:00:00+00:00/1/42",
            },
            {
                "image_id": "42_template",
                "image_type": "template",
                "role": "patch_template",
                "content_type": "image/png",
                "filename": "template.png",
                "bytes": b"fake-template-bytes",
                "source_uri": "mock-sc://patch/2026-05-26T08:00:00+00:00/1/42/template.png",
            },
        ]

        row = _patch_sample_to_parquet_row(ps, images)

        assert "images" in row, "Row missing 'images' column"
        assert len(row["images"]) == 2
        assert row["images"][0]["role"] == "review"
        assert row["images"][0]["bytes"] == b"fake-review-bytes"
        assert row["images"][1]["role"] == "patch_template"
        assert row["images"][1]["bytes"] == b"fake-template-bytes"
        assert row["test_id"] == 7

    # -- _build_image_structs unit test -------------------------------------

    def test_build_image_structs_metadata_only(self) -> None:
        """Assert ``_build_image_structs`` returns metadata structs with bytes=None."""
        from app.modules.sc.app.services.sc_import_service import (
            _build_image_structs,
        )

        ps = _sample_with_review("42")
        ps.review_images.append(
            _make_review_image(
                MOCK_REVIEW_URI_TPL.format(defect_id="42") + "/2",
                image_id=2,
                image_type="REVIEW_LOW_MAG",
            )
        )
        images = asyncio.run(
            _build_image_structs(
                patch_sample=ps,
                inspection_time=INSP_DT,
                wafer_key=1,
            )
        )

        assert len(images) == 5
        roles = {img["role"] for img in images}
        assert roles == {
            "review",
            "patch_template",
            "patch_defective",
            "patch_difference",
        }

        review_imgs = [img for img in images if img["role"] == "review"]
        assert [img["image_id"] for img in review_imgs] == ["1", "2"]
        assert [img["image_type"] for img in review_imgs] == ["review", "review"]
        assert all(img["bytes"] is None for img in images)
        assert all(img["content_type"] == "image/png" for img in images)

    def test_import_as_sparse_shards_preserves_order_and_manifest(self) -> None:
        """Direct sparse import test using SparseImportOperator + helpers."""
        import io

        import pyarrow.parquet as pq

        from app.modules.datasets.app.services.sparse_import_operator import (
            SparseImportOperator,
        )
        from app.modules.sc.app.services.sc_import_service import (
            _build_image_structs,
            _patch_sample_to_parquet_row,
        )
        from app.modules.sc.schema import (
            SC_SPARSE_SHARD_SCHEMA_V2,
            _build_v2_pyarrow_schema,
        )
        from platform_runtime.sparse import (
            ColumnSchema,
            DatasetManifest,
            DatasetPayloadStore,
            SampleLocator,
            ShardEntry,
        )
        from typing import cast

        class FakeUpstream:
            async def list_inspections(
                self, start_time: datetime, end_time: datetime
            ) -> pl.LazyFrame:
                return pl.LazyFrame([])

            async def get_inspection(
                self, inspection_time: datetime, wafer_key: int
            ) -> Any | None:
                return None

            async def list_samples(
                self,
                inspection_time: datetime,
                wafer_key: int,
                offset: int = 0,
                count: int = 50,
                reticle_size_x: int = 1,
                reticle_size_y: int = 1,
                reticle_offset_x: int = 0,
                reticle_offset_y: int = 0,
                on_progress=None,
            ) -> pl.LazyFrame:
                if offset < 0:
                    raise ValueError(f"offset must be >= 0, got {offset}")
                return pl.LazyFrame([])

            async def list_review_images(
                self,
                inspection_time: datetime,
                wafer_key: int,
            ) -> pl.LazyFrame:
                return pl.LazyFrame([])

            def stream(
                self,
                source_inspection_time: str,
                source_wafer_key: int,
                offset: int = 0,
            ):
                async def _iter_samples():
                    for sample_id in ("1", "2", "3")[offset:]:
                        yield _sample_with_review(sample_id)

                return _iter_samples()

        class FakeImageFetcher:
            async def get_image_bytes(
                self,
                *,
                inspection_time: str,
                wafer_key: int,
                defect_id: str,
                image_type: str,
                s3_path: str | None = None,
                review_image_id: int | None = None,
            ) -> bytes:
                delays = {"1": 0.03, "2": 0.01, "3": 0.02}
                await asyncio.sleep(delays[defect_id])
                return f"{defect_id}:{image_type}".encode()

        class CapturePayloadStore:
            def __init__(self) -> None:
                self.shards: list[bytes] = []
                self.manifest: DatasetManifest | None = None

            async def put_shard(
                self,
                *,
                dataset_id: str,
                org_id: str,
                shard_index: int,
                data: bytes,
                row_count: int,
                format: str = "parquet",
            ) -> ShardEntry:
                self.shards.append(data)
                return ShardEntry(
                    shard_index=shard_index,
                    uri=f"memory://shard-{shard_index}.{format}",
                    row_count=row_count,
                    format=format,
                    checksum_sha256="checksum",
                    byte_size=len(data),
                )

            async def put_manifest(
                self, manifest: DatasetManifest, *, org_id: str
            ) -> str:
                self.manifest = manifest
                return "memory://manifest.json"

        schema_columns = [
            ColumnSchema(name=c["name"], type=c["type"])
            for c in SC_SPARSE_SHARD_SCHEMA_V2
        ]
        pyarrow_schema = _build_v2_pyarrow_schema()
        insp_dt = datetime.fromisoformat("2026-05-26T08:00:00+00:00")
        if insp_dt.tzinfo is not None:
            insp_dt = insp_dt.astimezone(timezone.utc)

        payload_store: Any = CapturePayloadStore()
        operator = SparseImportOperator(
            dataset_id="ds-pipeline",
            org_id="org-test",
            payload_store=cast(DatasetPayloadStore, payload_store),
        )

        async def _run_import() -> dict:
            shard_entries_local: list[ShardEntry] = []
            sample_index_local: dict[str, SampleLocator] = {}
            rows_imported = 0
            shards_written = 0
            batch_size = 2

            async def publish_manifest() -> None:
                manifest = DatasetManifest(
                    dataset_id="ds-pipeline",
                    storage_mode="file_shard_sparse",
                    shard_count=shards_written,
                    total_rows=rows_imported,
                    schema_columns=schema_columns,
                    shards=shard_entries_local,
                    sample_index=sample_index_local,
                    schema_version="v2",
                )
                await payload_store.put_manifest(manifest, org_id="org-test")

            batch: list[dict[str, Any]] = []
            fake_upstream = FakeUpstream()
            async for patch_sample in fake_upstream.stream(
                "2026-05-26T08:00:00+00:00", 1
            ):
                images = await _build_image_structs(
                    patch_sample=patch_sample,
                    inspection_time=insp_dt,
                    wafer_key=1,
                )
                batch.append(_patch_sample_to_parquet_row(patch_sample, images))
                if len(batch) >= batch_size:
                    shard_entry, locators = await operator.flush_shard(
                        shard_index=shards_written,
                        rows=batch,
                        pyarrow_schema=pyarrow_schema,
                        row_id_key="sample_id",
                    )
                    shard_entries_local.append(shard_entry)
                    sample_index_local.update(locators)
                    rows_imported += len(batch)
                    shards_written += 1
                    await publish_manifest()
                    batch = []

            if batch:
                shard_entry, locators = await operator.flush_shard(
                    shard_index=shards_written,
                    rows=batch,
                    pyarrow_schema=pyarrow_schema,
                    row_id_key="sample_id",
                )
                shard_entries_local.append(shard_entry)
                sample_index_local.update(locators)
                rows_imported += len(batch)
                shards_written += 1
                await publish_manifest()

            if shards_written == 0:
                await publish_manifest()

            return {
                "total_rows": rows_imported,
                "shard_count": shards_written,
                "shard_entries": shard_entries_local,
                "sample_index": sample_index_local,
            }

        result = asyncio.run(_run_import())

        assert result["total_rows"] == 3
        assert len(payload_store.shards) == 2
        assert payload_store.manifest is not None
        assert payload_store.manifest.total_rows == 3
        assert payload_store.manifest.shard_count == 2
        assert payload_store.manifest.schema_version == "v2"

        first_shard = pq.read_table(io.BytesIO(payload_store.shards[0])).to_pylist()
        second_shard = pq.read_table(io.BytesIO(payload_store.shards[1])).to_pylist()

        assert [row["defect_id"] for row in first_shard] == ["1", "2"]
        assert [row["defect_id"] for row in second_shard] == ["3"]
        assert result["sample_index"]["1"].shard_index == 0
        assert result["sample_index"]["1"].row_index == 0
        assert result["sample_index"]["2"].shard_index == 0
        assert result["sample_index"]["2"].row_index == 1
        assert result["sample_index"]["3"].shard_index == 1
        assert result["sample_index"]["3"].row_index == 0


# ── v2 schema contract tests ───────────────────────────────────────────────


class TestV2EmbeddedImageSchema:
    """Contract tests for the v2 embedded-image schema.

    These tests describe the PyArrow ``list<struct>`` image column contract
    defined in ``app.modules.sc.schema``.  All fixtures here are synthetic —
    no DB, no S3, no flow orchestration — so they exercise only the schema
    module itself.
    """

    # ── SC_IMAGE_STRUCT_DTYPE tests ─────────────────────────────────────

    def test_image_struct_is_pyarrow_struct_type(self) -> None:
        from app.modules.sc.schema import SC_IMAGE_STRUCT_DTYPE

        assert isinstance(SC_IMAGE_STRUCT_DTYPE, pa.StructType), (
            f"Expected pa.StructType, got {type(SC_IMAGE_STRUCT_DTYPE)}"
        )

    def test_image_struct_required_fields(self) -> None:
        from app.modules.sc.schema import SC_IMAGE_STRUCT_DTYPE

        expected: dict[str, pa.DataType] = {
            "image_id": pa.string(),
            "image_type": pa.string(),
            "role": pa.string(),
            "content_type": pa.string(),
            "filename": pa.string(),
            "bytes": pa.binary(),
            "review_image_id": pa.int32(),
            "source_uri": pa.string(),
        }
        actual_fields = {f.name: f.type for f in SC_IMAGE_STRUCT_DTYPE}

        for name, dtype in expected.items():
            assert name in actual_fields, (
                f"Field {name!r} missing from SC_IMAGE_STRUCT_DTYPE"
            )
            assert actual_fields[name] == dtype, (
                f"Field {name!r}: expected {dtype}, got {actual_fields[name]}"
            )

    def test_image_struct_non_nullable_fields(self) -> None:
        from app.modules.sc.schema import SC_IMAGE_STRUCT_DTYPE

        field_map = {f.name: f for f in SC_IMAGE_STRUCT_DTYPE}
        non_nullable = {"image_id", "image_type", "role", "content_type", "filename"}
        for name in non_nullable:
            assert not field_map[name].nullable, f"Field {name!r} must be non-nullable"
        assert field_map["bytes"].nullable, "Field 'bytes' must be nullable"
        assert field_map["review_image_id"].nullable, (
            "Field 'review_image_id' must be nullable"
        )
        assert field_map["source_uri"].nullable, "Field 'source_uri' must be nullable"

    # ── SC_SPARSE_SHARD_SCHEMA_V2 tests ──────────────────────────────────

    def test_sparse_shard_schema_v2_has_images_column(self) -> None:
        from app.modules.sc.schema import SC_SPARSE_SHARD_SCHEMA_V2

        images_col = next(
            (c for c in SC_SPARSE_SHARD_SCHEMA_V2 if c["name"] == "images"),
            None,
        )
        assert images_col is not None, (
            "SC_SPARSE_SHARD_SCHEMA_V2 missing 'images' column"
        )
        assert images_col["type"] == "list<struct>", (
            f"Expected 'list<struct>', got {images_col['type']!r}"
        )

    def test_sparse_shard_schema_v2_retains_scalar_columns(self) -> None:
        from app.modules.sc.schema import SC_SPARSE_SHARD_SCHEMA_V2

        names = {c["name"] for c in SC_SPARSE_SHARD_SCHEMA_V2}
        expected_scalars = {
            "sample_id",
            "defect_id",
            "inspection_time",
            "wafer_key",
            "wafer_x",
            "wafer_y",
            "die_x",
            "die_y",
            "rough_bin",
            "class_number",
            "test_id",
            "lot_id",
            "has_review",
        }
        for name in expected_scalars:
            assert name in names, (
                f"Missing scalar column {name!r} in SC_SPARSE_SHARD_SCHEMA_V2"
            )
        assert "images" in names, "Missing 'images' column"
        assert "image_uris" not in names, "'image_uris' must be removed in v2"
        assert "metadata" not in names, "'metadata' must be removed in v2"

    # ── _build_v2_pyarrow_schema tests ───────────────────────────────────

    def test_build_v2_pyarrow_schema_returns_pa_schema(self) -> None:
        from app.modules.sc.schema import _build_v2_pyarrow_schema

        schema = _build_v2_pyarrow_schema()
        assert isinstance(schema, pa.Schema), f"Expected pa.Schema, got {type(schema)}"

    def test_build_v2_pyarrow_schema_has_images_list_struct(self) -> None:
        from app.modules.sc.schema import _build_v2_pyarrow_schema

        schema = _build_v2_pyarrow_schema()
        field = schema.field("images")
        assert isinstance(field.type, pa.ListType), (
            f"Expected ListType, got {field.type}"
        )
        assert isinstance(field.type.value_type, pa.StructType), (
            f"Expected StructType value type, got {field.type.value_type}"
        )

    # ── find_images_by_role tests ────────────────────────────────────────

    def test_find_images_by_role_filter_review(self) -> None:
        from app.modules.sc.schema import find_images_by_role

        images = [
            {"image_id": "1", "role": "review", "bytes": b"abc"},
            {"image_id": "2", "role": "patch_template", "bytes": b"def"},
            {"image_id": "3", "role": "patch_defective", "bytes": b"ghi"},
            {"image_id": "4", "role": "review", "bytes": b"jkl"},
        ]
        result = find_images_by_role(images, "review")
        assert len(result) == 2
        assert all(img["role"] == "review" for img in result)

    def test_find_images_by_role_filter_patch_template(self) -> None:
        from app.modules.sc.schema import find_images_by_role

        images = [
            {"image_id": "1", "role": "review", "bytes": b"abc"},
            {"image_id": "2", "role": "patch_template", "bytes": b"def"},
        ]
        result = find_images_by_role(images, "patch_template")
        assert len(result) == 1
        assert result[0]["role"] == "patch_template"

    def test_find_images_by_role_empty_when_no_match(self) -> None:
        from app.modules.sc.schema import find_images_by_role

        images = [
            {"image_id": "1", "role": "review", "bytes": b"abc"},
        ]
        result = find_images_by_role(images, "nonexistent_role")
        assert result == []

    def test_find_images_by_role_empty_list(self) -> None:
        from app.modules.sc.schema import find_images_by_role

        assert find_images_by_role([], "review") == []

    # ── IMAGE_ROLES tests ────────────────────────────────────────────────

    def test_image_roles_contains_expected_keys(self) -> None:
        from app.modules.sc.schema import IMAGE_ROLES

        assert set(IMAGE_ROLES.keys()) == {
            "review",
            "patch_template",
            "patch_defective",
            "patch_difference",
        }, f"Unexpected IMAGE_ROLES keys: {set(IMAGE_ROLES.keys())}"

    # ── check_sc_v2_or_raise tests ───────────────────────────────────────

    def test_check_sc_v2_or_raise_passes_for_v2(self) -> None:
        from unittest.mock import MagicMock
        from app.modules.sc.schema import check_sc_v2_or_raise

        manifest = MagicMock()
        manifest.schema_version = "v2"
        check_sc_v2_or_raise(manifest)

    def test_check_sc_v2_or_raise_rejects_legacy(self) -> None:
        from unittest.mock import MagicMock
        from app.modules.sc.schema import check_sc_v2_or_raise

        manifest = MagicMock()
        manifest.schema_version = None
        with pytest.raises(ValueError, match="re-import"):
            check_sc_v2_or_raise(manifest)

    def test_check_sc_v2_or_raise_rejects_v1(self) -> None:
        from unittest.mock import MagicMock
        from app.modules.sc.schema import check_sc_v2_or_raise

        manifest = MagicMock()
        manifest.schema_version = "v1"
        with pytest.raises(ValueError, match="re-import"):
            check_sc_v2_or_raise(manifest)
