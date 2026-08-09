from __future__ import annotations

from typing import Any, AsyncIterator

import polars as pl
import pyarrow.parquet as pq
import pytest

from app.modules.sc.materialization.app.services import (
    sc_inspection_materializer as materializer_module,
)
from app.modules.storage.domain.data_plane import DataPlaneSchemaRegistry
from app.modules.sc.materialization.app.services.sc_inspection_materializer import (
    ScInspectionMaterializer,
)
from app.modules.sc.wafer_data_gen import build_patch_sample


class _ImageSource:
    async def stream_inspection_images(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_ids: list[int],
        image_types: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        assert inspection_time == "2026-01-01T00:00:00"
        assert wafer_key == 42
        assert defect_ids == [7]
        assert image_types == ["patch_template", "patch_defective"]
        yield {
            "defect_id": "7",
            # The production image-parser normalizes requested patch aliases.
            "image_type": "Reference",
            "image_data": b"template",
        }
        yield {
            "defect_id": "7",
            "image_type": "Defective",
            "image_data": b"defective",
        }


class _UnexpectedImageSource:
    async def stream_inspection_images(
        self,
        **_kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        raise AssertionError("inline seed images must not call the upstream source")
        yield {}


@pytest.mark.asyncio
async def test_sc_materializer_cleans_partial_files_when_dataset_load_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("parquet unavailable")

    monkeypatch.setattr(materializer_module.pq, "ParquetWriter", fail_write)
    materializer = ScInspectionMaterializer(
        _ImageSource(),
        schema_registry=DataPlaneSchemaRegistry.default(),
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )

    with pytest.raises(RuntimeError, match="parquet unavailable"):
        await materializer.materialize(
            rows_lazyframe=pl.DataFrame(
                {
                    "sample_id": ["sample-1"],
                    "defect_id": ["7"],
                    "inspection_time": ["2026-01-01T00:00:00"],
                    "wafer_key": [42],
                    "wafer_x": [10],
                    "wafer_y": [11],
                    "rough_bin": [3],
                }
            ).lazy(),
            dataset_id="dataset-1",
            job_id="job-1",
            max_output_bytes=100_000_000,
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_sc_materializer_returns_parquet_without_runtime_dataset(
    tmp_path,
) -> None:
    materializer = ScInspectionMaterializer(
        _ImageSource(),
        schema_registry=DataPlaneSchemaRegistry.default(),
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )
    result = await materializer.materialize(
        rows_lazyframe=pl.DataFrame(
            {
                "sample_id": ["sample-1"],
                "defect_id": ["7"],
                "inspection_time": ["2026-01-01T00:00:00"],
                "wafer_key": [42],
                "wafer_x": [10],
                "wafer_y": [11],
                "rough_bin": [3],
            }
        ).lazy(),
        dataset_id="dataset-1",
        job_id="job-1",
        image_types=["patch_template", "patch_defective"],
        max_output_bytes=100_000_000,
    )
    try:
        table = pq.read_table(result.parquet_path)
        assert table.num_rows == 1
        assert table["patch_template_bytes"].to_pylist() == [b"template"]
        assert not hasattr(result, "dataset")
    finally:
        result.cleanup()


@pytest.mark.asyncio
async def test_sc_inspection_materializer_returns_data_plane_manifest(
    tmp_path,
) -> None:
    schema_registry = DataPlaneSchemaRegistry.default()
    materializer = ScInspectionMaterializer(
        _ImageSource(),
        schema_registry=schema_registry,
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )
    lf = pl.DataFrame(
        {
            "sample_id": ["sample-1"],
            "defect_id": ["7"],
            "inspection_time": ["2026-01-01T00:00:00"],
            "wafer_key": [42],
            "wafer_x": [10],
            "wafer_y": [11],
            "die_x": [1],
            "die_y": [2],
            "rough_bin": [3],
            "class_number": [4],
            "test_id": [99],
            "label": ["ng"],
        }
    ).lazy()

    result = await materializer.materialize(
        rows_lazyframe=lf,
        dataset_id="dataset-1",
        job_id="job-1",
        image_types=["patch_template", "patch_defective"],
        max_output_bytes=100_000_000,
    )
    try:
        assert result.row_count == 1
        assert result.manifest.view_contract == "sc.patch_image.v1"
        assert result.manifest.schema_ref == "arrow-schema://sc.patch_image.v1/1"
        assert result.manifest.dataset_id == "dataset-1"
        assert result.manifest.job_id == "job-1"
        assert result.manifest.image_roles == ("patch_template", "patch_defective")
        assert result.manifest.shards[0].uri == f"file://{result.parquet_path}"
        assert result.manifest.shards[0].row_count == 1

        table = pq.read_table(result.parquet_path)
        expected_schema = schema_registry.get("sc.patch_image.v1", "1")
        assert pq.read_schema(result.parquet_path).equals(expected_schema)
        assert table.schema.equals(expected_schema)
        assert table.schema.field("test_id").nullable is True
        assert table.column("test_id").to_pylist() == [99]
        assert table.column("patch_template_bytes").to_pylist() == [b"template"]
        assert table.column("patch_defective_bytes").to_pylist() == [b"defective"]
    finally:
        result.cleanup()


@pytest.mark.asyncio
async def test_sc_materializer_empty_output_uses_registered_schema(tmp_path) -> None:
    schema_registry = DataPlaneSchemaRegistry.default()
    materializer = ScInspectionMaterializer(
        _UnexpectedImageSource(),
        schema_registry=schema_registry,
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )

    result = await materializer.materialize(
        rows_lazyframe=pl.DataFrame(
            schema={
                "sample_id": pl.String,
                "defect_id": pl.String,
                "inspection_time": pl.String,
                "wafer_key": pl.Int64,
            }
        ).lazy(),
        dataset_id="dataset-1",
        job_id="job-1",
        max_output_bytes=100_000_000,
    )
    try:
        assert result.row_count == 0
        assert pq.read_schema(result.parquet_path).equals(
            schema_registry.get("sc.patch_image.v1", "1")
        )
    finally:
        result.cleanup()


@pytest.mark.asyncio
async def test_sc_materializer_rejects_columns_outside_view_contract(tmp_path) -> None:
    materializer = ScInspectionMaterializer(
        _UnexpectedImageSource(),
        schema_registry=DataPlaneSchemaRegistry.default(),
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )

    with pytest.raises(ValueError, match="patch_difference_bytes"):
        await materializer.materialize(
            rows_lazyframe=pl.DataFrame().lazy(),
            image_types=["patch_difference"],
            max_output_bytes=100_000_000,
        )


@pytest.mark.asyncio
async def test_sc_materializer_uses_inline_seed_images_before_upstream(
    tmp_path,
) -> None:
    sample = build_patch_sample(0)
    lf = pl.DataFrame(
        [
            {
                "id": "sample-1",
                "image_uris": [
                    image.image_id for image in sample.shard_images
                ],
                "metadata_json": {
                    "sample_id": "sample-1",
                    "defect_id": sample.defect_id,
                    "inspection_time": sample.inspection_time.isoformat()
                    if sample.inspection_time
                    else "",
                    "wafer_key": sample.wafer_key,
                    "wafer_x": sample.wafer_x,
                    "wafer_y": sample.wafer_y,
                    "rough_bin": sample.rough_bin,
                    "shard_images": [
                        image.model_dump(mode="json")
                        for image in sample.shard_images
                    ],
                },
                "label": "Scratch",
            }
        ],
        infer_schema_length=None,
    ).lazy()
    materializer = ScInspectionMaterializer(
        _UnexpectedImageSource(),
        schema_registry=DataPlaneSchemaRegistry.default(),
        batch_rows=2,
        max_error_records=100,
        temp_dir=str(tmp_path),
    )

    result = await materializer.materialize(
        rows_lazyframe=lf,
        dataset_id="dataset-1",
        job_id="prediction-job-1",
        image_types=["patch_template", "patch_defective"],
        max_output_bytes=100_000_000,
    )
    try:
        table = pq.read_table(result.parquet_path)
        template = table.column("patch_template_bytes").to_pylist()[0]
        defective = table.column("patch_defective_bytes").to_pylist()[0]
        assert template.startswith(b"\x89PNG\r\n\x1a\n")
        assert defective.startswith(b"\x89PNG\r\n\x1a\n")
        assert result.errors == []
    finally:
        result.cleanup()
