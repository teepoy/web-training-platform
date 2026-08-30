from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from klarf import Klarf12ImageList, KlarfArray, KlarfSymbol, loads
from klarf.v12 import loads12
from sampling_rules import RandomCountRule, ReviewSamplingProgram

from app.modules.sc.app.services import prediction_export_service as export_module
from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
)
from app.modules.sc.app.services.prediction_export_service import (
    ScPredictionExportError,
    ScPredictionExportService,
)
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
    ScPredictionExportResultSource,
)
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    TaskSpec,
)


class _ArtifactStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_file(
        self,
        object_name: str,
        path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self.objects[object_name] = Path(path).read_bytes()
        return f"memory://{object_name}"

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self.objects[object_name] = data
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        return self.objects[uri.removeprefix("memory://")]

    async def get_file(self, uri: str, destination: str) -> None:
        Path(destination).write_bytes(await self.get_bytes(uri))

    async def get_size(self, uri: str) -> int:
        return len(await self.get_bytes(uri))

    async def iter_bytes(
        self,
        uri: str,
        *,
        offset: int = 0,
        length: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        data = await self.get_bytes(uri)
        end = len(data) if length is None else offset + length
        for position in range(offset, min(end, len(data)), chunk_size):
            yield data[position : min(position + chunk_size, end)]

    async def delete(self, uri: str) -> None:
        self.objects.pop(uri.removeprefix("memory://"), None)

    async def list_prefix(self, prefix: str) -> list[str]:
        return [
            f"memory://{name}"
            for name in sorted(self.objects)
            if name.startswith(prefix)
        ]


class _Upstream:
    def __init__(self, frames: dict[int, pl.LazyFrame]) -> None:
        self._frames = frames

    async def get_sample_count(self, _time: datetime, wafer_key: int) -> int:
        return self._frames[wafer_key].collect().height

    async def stream_sample_batches(
        self, _time: datetime, wafer_key: int, **_kwargs: object
    ):
        table = self._frames[wafer_key].collect().to_arrow()
        for batch in table.to_batches():
            assert isinstance(batch, pa.RecordBatch)
            yield batch

    async def stream_membership_sample_batches(
        self,
        _time: datetime,
        wafer_key: int,
        *,
        defect_ids: Sequence[int],
        projection: Sequence[str] | None,
        **_kwargs: object,
    ):
        frame = (
            self._frames[wafer_key]
            .collect()
            .filter(pl.col("defect_id").cast(pl.Int64).is_in(defect_ids))
        )
        if projection is not None:
            frame = frame.select(projection)
        for batch in frame.to_arrow().to_batches():
            assert isinstance(batch, pa.RecordBatch)
            yield batch


class _ImageResolver:
    def __init__(
        self,
        *,
        fail_sample_id: str | None = None,
        content_type: str = "image/png",
    ) -> None:
        self.received_sample_ids: list[str] = []
        self.call_sizes: list[int] = []
        self.fail_sample_id = fail_sample_id
        self.content_type = content_type

    async def resolve_images(
        self,
        *,
        roles: Sequence[str],
        items: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        assert tuple(roles) == ("patch_defective",)
        self.call_sizes.append(len(items))
        results: list[dict[str, object]] = []
        for item in items:
            sample_id = str(item["sample_id"])
            self.received_sample_ids.append(sample_id)
            results.append(
                {
                    **item,
                    "error": "",
                    "images": [
                        {
                            "role": "patch_defective",
                            "image_data": f"png:{sample_id}".encode(),
                            "content_type": self.content_type,
                            "error": (
                                "source image missing"
                                if sample_id == self.fail_sample_id
                                else ""
                            ),
                        }
                    ],
                }
            )
        return results


class _ImageSourceFactory:
    def __init__(self, resolver: _ImageResolver) -> None:
        self.resolver = resolver

    @asynccontextmanager
    async def open(self) -> AsyncIterator[_ImageResolver]:
        yield self.resolver


def _frame(
    *,
    inspection_time: str = "2026-08-19T00:00:00",
    wafer_key: int = 17,
    sample_prefix: str = "sample",
) -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "sample_id": [
                f"{sample_prefix}-1",
                f"{sample_prefix}-2",
                f"{sample_prefix}-3",
            ],
            "inspection_time": [inspection_time] * 3,
            "wafer_key": [wafer_key, wafer_key, wafer_key],
            "defect_id": ["1", "2", "3"],
            "wafer_x": [10.0, 20.0, 30.0],
            "wafer_y": [11.0, 21.0, 31.0],
            "index_x": [1, 1, 2],
            "index_y": [1, 1, 2],
            "size_x": [3.0, 4.0, 5.0],
            "size_y": [4.0, 5.0, 6.0],
            "size_d": [5.0, 6.0, 7.0],
            "area": [12.0, 20.0, 30.0],
            "class_number": [10, 20, 30],
            "test_id": [1, 1, 1],
            "cluster_id": [0, 5, 0],
            "repeater_id": [0, 0, 9],
            "rough_bin": [1, 2, 3],
            "final_bin": [4, 5, 6],
            "images": [3, 0, 1],
            "label": [None, "60", "0"],
            "predicted_label": ["40", "50", "70"],
            "confidence": [0.8, 0.9, 0.7],
            "lot_id": ["LOT-042"] * 3,
            "wafer_id": ["WAFER-17"] * 3,
            "device": ["DEVICE-A"] * 3,
            "layer_id": ["METAL-1"] * 3,
            "inspect_equip_id": ["KLA-01"] * 3,
            "recipe_id": ["RECIPE-A"] * 3,
            "center_x": [1000] * 3,
            "center_y": [2000] * 3,
            "origin_x": [10] * 3,
            "origin_y": [20] * 3,
            "die_size_x": [800] * 3,
            "die_size_y": [500] * 3,
        }
    ).lazy()


def _service(
    image_resolver: _ImageResolver | None = None,
    *,
    image_batch_rows: int = 512,
) -> tuple[ScPredictionExportService, _ArtifactStorage]:
    dataset = Dataset(
        id="dataset-1",
        name="Inspection 17",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc"),
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-20T01:02:03+00:00",
            "source_wafer_key": 17,
        },
    )
    repository = AsyncMock()
    repository.get_dataset = AsyncMock(return_value=dataset)
    dataset_storage = AsyncMock()
    dataset_storage.list_samples = AsyncMock(return_value=_frame())
    storage_factory = AsyncMock()
    storage_factory.open = AsyncMock(return_value=dataset_storage)
    collection_reader = AsyncMock()
    artifacts = _ArtifactStorage()
    image_resolver = image_resolver or _ImageResolver()
    return (
        ScPredictionExportService(
            repository=repository,
            collection_reader=collection_reader,
            storage_factory=storage_factory,
            artifact_storage=artifacts,
            image_stream_factory=_ImageSourceFactory(image_resolver),
            image_batch_rows=image_batch_rows,
            upstream_reader=cast(ScUpstreamReader, _Upstream({17: _frame()})),
            source_batch_rows=512,
        ),
        artifacts,
    )


@pytest.mark.asyncio
async def test_parquet_export_contains_current_prediction_and_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, artifacts = _service()
    monkeypatch.setattr(
        export_module,
        "_collect_export_frame",
        lambda _frame: pytest.fail("unsampled Parquet must not collect all rows"),
    )

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.PARQUET,
        sampling_program=None,
        sampling_seed=None,
    )

    table = pq.read_table(io.BytesIO(next(iter(artifacts.objects.values()))))
    assert result.row_count == 3
    assert "/exports/orgs/org-1/datasets/dataset-1/" in result.uri
    rows = {row["sample_id"]: row for row in table.to_pylist()}
    assert rows["sample-1"]["predicted_label"] == "40"
    assert rows["sample-2"]["predicted_label"] == "50"
    assert rows["sample-3"]["predicted_label"] == "70"
    assert rows["sample-1"]["final_class"] == "40"
    assert rows["sample-2"]["final_class"] == "60"
    assert rows["sample-3"]["final_class"] == "70"


@pytest.mark.asyncio
async def test_annotation_result_export_omits_unclassified_rows() -> None:
    service, artifacts = _service()

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.PARQUET,
        result_source=ScPredictionExportResultSource.ANNOTATION,
        sampling_program=None,
        sampling_seed=None,
    )

    table = pq.read_table(io.BytesIO(next(iter(artifacts.objects.values()))))
    rows = table.to_pylist()
    assert result.row_count == 1
    assert [row["sample_id"] for row in rows] == ["sample-2"]
    assert rows[0]["final_class"] == "60"


@pytest.mark.asyncio
async def test_prediction_result_export_uses_predictions_and_omits_only_missing_results() -> (
    None
):
    service, artifacts = _service()

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.PARQUET,
        result_source=ScPredictionExportResultSource.PREDICTION,
        sampling_program=None,
        sampling_seed=None,
    )

    table = pq.read_table(io.BytesIO(next(iter(artifacts.objects.values()))))
    rows = {row["sample_id"]: row for row in table.to_pylist()}
    assert result.row_count == 3
    assert {sample_id: row["final_class"] for sample_id, row in rows.items()} == {
        "sample-1": "40",
        "sample-2": "50",
        "sample-3": "70",
    }


@pytest.mark.asyncio
async def test_export_applies_review_sampling_extra_filter_before_rules() -> None:
    service, artifacts = _service()

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.PARQUET,
        result_source=ScPredictionExportResultSource.FINAL_CLASS,
        sampling_program=ReviewSamplingProgram(rules=(RandomCountRule(count=10),)),
        sampling_seed=42,
        sampling_extra_filter={
            "combinator": "and",
            "items": [
                {
                    "kind": "condition",
                    "field": "images",
                    "condition": {
                        "filterType": "number",
                        "type": "inRange",
                        "filter": 1,
                        "filterTo": 10,
                    },
                }
            ],
        },
    )

    table = pq.read_table(io.BytesIO(next(iter(artifacts.objects.values()))))
    assert result.row_count == 2
    assert {row["sample_id"] for row in table.to_pylist()} == {"sample-1", "sample-3"}


@pytest.mark.asyncio
async def test_klarf_export_uses_annotation_sampling_result() -> None:
    service, artifacts = _service()

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.KLARF,
        sampling_program=ReviewSamplingProgram(rules=(RandomCountRule(count=2),)),
        sampling_seed=42,
    )

    content = next(iter(artifacts.objects.values())).decode("utf-8")
    document = loads12(content)
    defect_list = document.find_tables("DefectList")[0]
    assert result.row_count == 2
    assert result.sampled is True
    assert result.filename == "METAL-1-LOT-042-WAFER-17.000"
    assert len(defect_list.rows) == 2
    assert len({row[0] for row in defect_list.rows}) == 2
    assert all(row[15] == 0 for row in defect_list.rows)
    assert all(row[16] == Klarf12ImageList(items=()) for row in defect_list.rows)
    assert defect_list.columns == (
        "DEFECTID",
        "XREL",
        "YREL",
        "XINDEX",
        "YINDEX",
        "XSIZE",
        "YSIZE",
        "DEFECTAREA",
        "DSIZE",
        "CLASSNUMBER",
        "TEST",
        "CLUSTERNUMBER",
        "ROUGHBINNUMBER",
        "FINEBINNUMBER",
        "REVIEWSAMPLE",
        "IMAGECOUNT",
        "IMAGELIST",
    )
    assert "FINALCLASS" not in defect_list.columns
    assert "PREDICTIONLABEL" not in defect_list.columns
    assert document.find_records("LotID")[0].values == ("LOT-042",)
    assert document.find_records("WaferID")[0].values == ("WAFER-17",)
    assert document.find_records("DeviceID")[0].values == ("DEVICE-A",)
    assert document.find_records("StepID")[0].values == ("METAL-1",)
    assert content.startswith("FileVersion 1 2;\n")
    assert content.endswith("EndOfFile;\n")
    assert "FileTimestamp " in content
    assert "ResultTimestamp 08-19-26 00:00:00;" in content


@pytest.mark.asyncio
async def test_prediction_export_rejects_non_sc_dataset_type() -> None:
    service, _artifacts = _service()
    get_dataset = cast(AsyncMock, service._repository.get_dataset)  # type: ignore[attr-defined]
    dataset = get_dataset.return_value
    get_dataset.return_value = dataset.model_copy(
        update={"dataset_type": "image_classification"}
    )

    with pytest.raises(ScPredictionExportError, match="requires an image_sc dataset"):
        await service.export(
            dataset_id="dataset-1",
            org_id="org-1",
            created_by="user-1",
            export_format=ScPredictionExportFormat.KLARF,
            sampling_program=None,
            sampling_seed=None,
        )


@pytest.mark.asyncio
async def test_klarf_image_export_resolves_sampled_rows_and_packages_exact_references() -> (
    None
):
    image_resolver = _ImageResolver()
    service, artifacts = _service(image_resolver)

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.KLARF,
        sampling_program=ReviewSamplingProgram(rules=(RandomCountRule(count=2),)),
        sampling_seed=42,
        include_images=True,
    )

    assert result.row_count == 2
    assert result.filename.endswith(".zip")
    assert len(image_resolver.received_sample_ids) == 2
    with zipfile.ZipFile(io.BytesIO(next(iter(artifacts.objects.values())))) as archive:
        names = set(archive.namelist())
        image_names = {name for name in names if name.startswith("images/")}
        klarf_name = next(name for name in names if name.endswith(".000"))
        document = loads12(archive.read(klarf_name).decode("utf-8"))
        image_references = {
            (
                record.values[0].value
                if isinstance(record.values[0], KlarfSymbol)
                else str(record.values[0])
            )
            for record in document.find_records("TiffFileName")
        }
        defect_rows = [
            row for table in document.find_tables("DefectList") for row in table.rows
        ]

        assert image_names == image_references
        assert len(image_names) == 2
        assert all(
            archive.read(name).startswith(b"png:sample-") for name in image_names
        )
        assert all(row[15] == 1 for row in defect_rows)
        assert all(row[16] == Klarf12ImageList(items=((1, 0),)) for row in defect_rows)
        manifest = archive.read("manifest.json")
        assert b'"image_binaries_included": true' in manifest
        assert b'"image_count": 2' in manifest


@pytest.mark.asyncio
async def test_klarf_18_image_export_packages_all_rows_in_bounded_batches() -> None:
    image_resolver = _ImageResolver()
    service, artifacts = _service(image_resolver, image_batch_rows=2)

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.KLARF,
        klarf_version=ScKlarfVersion.V1_8,
        sampling_program=None,
        sampling_seed=None,
        include_images=True,
    )

    assert result.row_count == 3
    assert image_resolver.call_sizes == [2, 1]
    with zipfile.ZipFile(io.BytesIO(next(iter(artifacts.objects.values())))) as archive:
        names = set(archive.namelist())
        image_names = {name for name in names if name.startswith("images/")}
        klarf_name = next(name for name in names if name.endswith(".000"))
        document = loads(archive.read(klarf_name).decode("utf-8"))
        wafer = document.find_records("WaferRecord")[0]
        image_values = [row[15] for row in wafer.find_lists("DefectList")[0].rows]

        assert len(image_names) == 3
        assert all(isinstance(value, KlarfArray) for value in image_values)
        assert {
            str(value.items[0][0])
            for value in image_values
            if isinstance(value, KlarfArray)
        } == image_names


@pytest.mark.asyncio
async def test_klarf_image_export_fails_without_persisting_partial_artifact() -> None:
    image_resolver = _ImageResolver(fail_sample_id="sample-2")
    service, artifacts = _service(image_resolver)

    with pytest.raises(ScPredictionExportError, match="source image missing"):
        await service.export(
            dataset_id="dataset-1",
            org_id="org-1",
            created_by="user-1",
            export_format=ScPredictionExportFormat.KLARF,
            sampling_program=None,
            sampling_seed=None,
            include_images=True,
        )

    assert artifacts.objects == {}


@pytest.mark.asyncio
async def test_klarf_18_export_uses_hierarchical_records() -> None:
    service, artifacts = _service()

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.KLARF,
        klarf_version=ScKlarfVersion.V1_8,
        sampling_program=None,
        sampling_seed=None,
    )

    content = next(iter(artifacts.objects.values())).decode("utf-8")
    document = loads(content)
    lot = document.find_records("LotRecord")[0]
    wafer = lot.find_records("WaferRecord")[0]
    defects = wafer.find_lists("DefectList")[0]
    summary = wafer.find_records("SummaryRecord")[0]

    assert result.klarf_version is ScKlarfVersion.V1_8
    assert document.version == "1.8"
    assert lot.identifiers == ("LOT-042",)
    assert wafer.identifiers == ("WAFER-17",)
    assert len(defects.rows) == 3
    assert {row[9] for row in defects.rows} == {40, 60, 70}
    assert all(row[15] == KlarfSymbol("N") for row in defects.rows)
    assert summary.find_lists("TestSummaryList")[0].rows == ((1, 3),)


@pytest.mark.asyncio
async def test_klarf_export_requires_complete_wafer_geometry() -> None:
    service, _artifacts = _service()
    service._upstream_reader = _Upstream(  # type: ignore[assignment]
        {17: _frame().drop("die_size_x", "die_size_y")}
    )

    with pytest.raises(ScPredictionExportError, match="die_size_x"):
        await service.export(
            dataset_id="dataset-1",
            org_id="org-1",
            created_by="user-1",
            export_format=ScPredictionExportFormat.KLARF,
            sampling_program=None,
            sampling_seed=None,
        )


@pytest.mark.asyncio
async def test_zip_export_packages_parquet_klarf_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, artifacts = _service()
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 100)

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.ZIP,
        klarf_version=ScKlarfVersion.V1_8,
        sampling_program=ReviewSamplingProgram(rules=(RandomCountRule(count=2),)),
        sampling_seed=17,
    )

    with zipfile.ZipFile(io.BytesIO(next(iter(artifacts.objects.values())))) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert any(name.endswith(".000") for name in names)
        assert any(name.endswith(".parquet") for name in names)
        manifest = archive.read("manifest.json")
        assert b'"image_binaries_included": false' in manifest
        assert b'"klarf_version": "1.8"' in manifest
        assert b'"type": "random_count"' in manifest
        parquet_name = next(name for name in names if name.endswith(".parquet"))
        assert archive.getinfo(parquet_name).compress_type == zipfile.ZIP_STORED
        assert archive.getinfo(parquet_name).extract_version >= 45
        assert pq.read_table(io.BytesIO(archive.read(parquet_name))).num_rows == 2
        klarf_name = next(name for name in names if name.endswith(".000"))
        assert archive.getinfo(klarf_name).compress_type == zipfile.ZIP_DEFLATED
        klarf = loads(archive.read(klarf_name).decode("utf-8"))
        lot = klarf.find_records("LotRecord")[0]
        wafer = lot.find_records("WaferRecord")[0]
        assert len(wafer.find_lists("DefectList")[0].rows) == 2
    assert result.row_count == 2
    assert result.klarf_version is ScKlarfVersion.V1_8


@pytest.mark.asyncio
async def test_klarf_export_ignores_stale_source_fields_in_legacy_shards() -> None:
    service, artifacts = _service()
    storage = service._storage_factory.open.return_value  # type: ignore[attr-defined]
    storage.list_samples.return_value = _frame().with_columns(
        pl.lit("STALE-LOT").alias("lot_id"),
        pl.lit("STALE-WAFER").alias("wafer_id"),
    )

    result = await service.export(
        dataset_id="dataset-1",
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.KLARF,
        sampling_program=None,
        sampling_seed=None,
    )

    assert result.filename.endswith(".000")
    content = next(iter(artifacts.objects.values())).decode("utf-8")
    document = loads12(content)
    assert document.find_records("LotID")[0].values == ("LOT-042",)
    assert document.find_records("WaferID")[0].values == ("WAFER-17",)


@pytest.mark.asyncio
async def test_collection_export_packages_only_selected_members_by_inspection() -> None:
    dataset_1 = Dataset(
        id="dataset-1",
        name="Inspection 17",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc"),
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-20T01:02:03+00:00",
            "source_wafer_key": 17,
        },
    )
    dataset_2 = dataset_1.model_copy(
        update={
            "id": "dataset-2",
            "name": "Inspection 18",
            "dataset_meta": {
                "source_inspection_time": "2026-08-20T01:02:03+00:00",
                "source_wafer_key": 18,
            },
        }
    )
    repository = AsyncMock()
    repository.list_datasets_by_ids = AsyncMock(return_value=[dataset_1, dataset_2])
    collection_reader = AsyncMock()
    collection_reader.get_collection = AsyncMock(
        return_value=DatasetCollection(
            id="collection-1",
            org_id="org-1",
            name="Selected inspections",
            description="",
            target_view_id="sc:patch-image@v1",
            target_view_contract="sc.patch-image.v1",
            target_schema_version="1",
            duplicate_policy="keep_all",
            missing_data_policy="fail",
            definition_version=1,
            created_by="user-1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    collection_reader.list_members = AsyncMock(
        return_value=[
            DatasetCollectionMember(
                id="member-1",
                collection_id="collection-1",
                source_dataset_id="dataset-1",
                position=0,
                linked_definition_version=1,
                unlinked_definition_version=None,
                filter_spec={},
                label_mapping={},
                sampling_spec={},
                linked_by="user-1",
                linked_at=datetime.now(timezone.utc),
                unlinked_by=None,
                unlinked_at=None,
            ),
            DatasetCollectionMember(
                id="member-2",
                collection_id="collection-1",
                source_dataset_id="dataset-2",
                position=1,
                linked_definition_version=1,
                unlinked_definition_version=None,
                filter_spec={},
                label_mapping={},
                sampling_spec={},
                linked_by="user-1",
                linked_at=datetime.now(timezone.utc),
                unlinked_by=None,
                unlinked_at=None,
            ),
        ]
    )
    storage_1 = AsyncMock()
    storage_1.list_samples = AsyncMock(return_value=_frame())
    storage_2 = AsyncMock()
    storage_2.list_samples = AsyncMock(
        return_value=_frame(
            inspection_time="2026-08-20T01:02:03",
            wafer_key=18,
            sample_prefix="second",
        )
    )
    storage_factory = AsyncMock()
    storage_factory.open = AsyncMock(side_effect=[storage_1, storage_2])
    artifacts = _ArtifactStorage()
    service = ScPredictionExportService(
        repository=repository,
        collection_reader=collection_reader,
        storage_factory=storage_factory,
        artifact_storage=artifacts,
        image_stream_factory=_ImageSourceFactory(_ImageResolver()),
        image_batch_rows=512,
        upstream_reader=cast(
            ScUpstreamReader,
            _Upstream(
                {
                    17: _frame(),
                    18: _frame(
                        inspection_time="2026-08-20T01:02:03",
                        wafer_key=18,
                        sample_prefix="second",
                    ),
                }
            ),
        ),
        source_batch_rows=512,
    )

    result = await service.export_collection(
        collection_id="collection-1",
        member_ids=("member-1", "member-2"),
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.ZIP,
        sampling_program=None,
        sampling_seed=None,
        include_images=True,
    )

    package = next(iter(artifacts.objects.values()))
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        parquet_name = next(
            name for name in archive.namelist() if name.endswith(".parquet")
        )
        table = pq.read_table(io.BytesIO(archive.read(parquet_name)))
        klarf_names = sorted(
            name for name in archive.namelist() if name.endswith((".000", ".001"))
        )
        image_names = {
            name for name in archive.namelist() if name.startswith("images/")
        }
        assert len(klarf_names) == 2
        referenced_images: set[str] = set()
        for name in klarf_names:
            document = loads12(archive.read(name).decode("utf-8"))
            assert (
                sum(
                    len(defect_table.rows)
                    for defect_table in document.find_tables("DefectList")
                )
                == 3
            )
            referenced_images.update(
                value.value if isinstance(value, KlarfSymbol) else str(value)
                for record in document.find_records("TiffFileName")
                for value in record.values
            )
        assert len(image_names) == 6
        assert referenced_images == image_names
    assert result.row_count == 6
    assert set(table.column("source_dataset_id").to_pylist()) == {
        "dataset-1",
        "dataset-2",
    }
    repository.list_datasets_by_ids.assert_awaited_once_with(
        ["dataset-1", "dataset-2"], org_id="org-1"
    )
    assert storage_factory.open.await_count == 2


@pytest.mark.asyncio
async def test_collection_sampling_identity_includes_source_dataset() -> None:
    dataset_1 = Dataset(
        id="dataset-1",
        name="Inspection 17",
        dataset_type="image_sc",
        task_spec=TaskSpec(task_type="sc"),
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "source_inspection_time": "2026-08-20T01:02:03+00:00",
            "source_wafer_key": 17,
        },
    )
    dataset_2 = dataset_1.model_copy(
        update={
            "id": "dataset-2",
            "name": "Inspection 17 duplicate IDs",
            "dataset_meta": {
                "source_inspection_time": "2026-08-20T01:02:03+00:00",
                "source_wafer_key": 18,
            },
        }
    )
    repository = AsyncMock()
    repository.list_datasets_by_ids = AsyncMock(return_value=[dataset_1, dataset_2])
    collection_reader = AsyncMock()
    collection_reader.get_collection = AsyncMock(
        return_value=DatasetCollection(
            id="collection-1",
            org_id="org-1",
            name="Duplicate sample IDs",
            description="",
            target_view_id="sc:patch-image@v1",
            target_view_contract="sc.patch-image.v1",
            target_schema_version="1",
            duplicate_policy="keep_all",
            missing_data_policy="fail",
            definition_version=1,
            created_by="user-1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    collection_reader.list_members = AsyncMock(
        return_value=[
            DatasetCollectionMember(
                id=f"member-{index}",
                collection_id="collection-1",
                source_dataset_id=f"dataset-{index}",
                position=index,
                linked_definition_version=1,
                unlinked_definition_version=None,
                filter_spec={},
                label_mapping={},
                sampling_spec={},
                linked_by="user-1",
                linked_at=datetime.now(timezone.utc),
                unlinked_by=None,
                unlinked_at=None,
            )
            for index in (1, 2)
        ]
    )
    storage_1 = AsyncMock()
    storage_1.list_samples = AsyncMock(return_value=_frame())
    storage_2 = AsyncMock()
    storage_2.list_samples = AsyncMock(return_value=_frame())
    storage_factory = AsyncMock()
    storage_factory.open = AsyncMock(side_effect=[storage_1, storage_2])
    artifacts = _ArtifactStorage()
    service = ScPredictionExportService(
        repository=repository,
        collection_reader=collection_reader,
        storage_factory=storage_factory,
        artifact_storage=artifacts,
        image_stream_factory=_ImageSourceFactory(_ImageResolver()),
        image_batch_rows=512,
        upstream_reader=cast(ScUpstreamReader, _Upstream({17: _frame(), 18: _frame()})),
        source_batch_rows=512,
    )

    result = await service.export_collection(
        collection_id="collection-1",
        member_ids=("member-1", "member-2"),
        org_id="org-1",
        created_by="user-1",
        export_format=ScPredictionExportFormat.PARQUET,
        sampling_program=ReviewSamplingProgram(rules=(RandomCountRule(count=1),)),
        sampling_seed=42,
    )

    table = pq.read_table(io.BytesIO(next(iter(artifacts.objects.values()))))
    assert result.row_count == 1
    assert table.num_rows == 1
