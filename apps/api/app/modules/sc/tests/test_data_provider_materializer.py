from __future__ import annotations

import asyncio
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.sc.data_provider.cache import CachedDataObject, ScDataObjectCache
from app.modules.sc.data_provider.materializer import (
    ScCollectionTooLargeError,
    ScDataMaterializer,
)
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.domain.models import ScInspectionRecord
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.domain.protocols import ArtifactStorage


def _cached_object(path: Path, object_id: str) -> CachedDataObject:
    return CachedDataObject(
        object_id=object_id,
        path=path,
        size_bytes=1,
        scope="org:org-1:dataset:dataset-1",
        revision=0,
        cache_status="hit",
    )


def _ready_revision(manifest_uri: str) -> DatasetCollectionRevision:
    return DatasetCollectionRevision(
        id="revision-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=2,
        definition_hash="a" * 64,
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch_image.v1",
        target_schema_version="1",
        status="ready",
        source_snapshot=(
            {"source_dataset_id": "dataset-a"},
            {"source_dataset_id": "dataset-b"},
        ),
        row_count=2,
        label_counts={},
        manifest_uri=manifest_uri,
        provenance_uri=None,
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=datetime.now(timezone.utc),
        error_code=None,
        error_detail=None,
    )


def _inspection(wafer_key: int, *, latest_update: int = 1) -> ScInspectionRecord:
    return ScInspectionRecord(
        inspection_time=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
        wafer_key=wafer_key,
        device=f"device-{wafer_key}",
        latest_update=latest_update,
    )


@pytest.mark.asyncio
async def test_collection_materialization_rejects_browser_unsafe_row_count() -> None:
    revision_reader = AsyncMock(spec=DatasetCollectionRevisionReaderPort)
    revision_reader.get_revision.return_value = replace(
        _ready_revision("memory://revision"), row_count=300_001
    )
    materializer = ScDataMaterializer(
        upstream_reader=AsyncMock(spec=ScUpstreamReader),
        storage_factory=AsyncMock(spec=DatasetStorageFactoryPort),
        collection_revision_reader=revision_reader,
        artifact_storage=AsyncMock(spec=ArtifactStorage),
        cache=AsyncMock(spec=ScDataObjectCache),
        batch_rows=50_000,
        classify_max_rows=300_000,
    )

    with pytest.raises(ScCollectionTooLargeError, match="300001 rows"):
        await materializer.materialize(
            ScDataScope.collection(
                collection_id="collection-1",
                revision_id="revision-1",
                org_id="org-1",
            ),
            revision=1,
        )


@pytest.mark.asyncio
async def test_dataset_cache_hits_use_dataset_metadata_without_scanning_samples(
    tmp_path: Path,
) -> None:
    storage = AsyncMock()
    storage.get_dataset_metadata.return_value = SimpleNamespace(
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        }
    )
    storage.annotation_overlay_lazyframe.return_value = (None, "0" * 64)
    storage.prediction_overlay_lazyframe.return_value = (None, "0" * 64)
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.return_value = storage
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.return_value = _inspection(1)
    cache = AsyncMock(spec=ScDataObjectCache)
    review_images = _cached_object(tmp_path / "review.parquet", "review")
    samples_base = _cached_object(tmp_path / "samples.parquet", "samples")
    cache.get_or_build.return_value = review_images
    cache.get_or_build_file.return_value = samples_base
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        artifact_storage=AsyncMock(spec=ArtifactStorage),
        cache=cache,
        batch_rows=50_000,
        classify_max_rows=300_000,
    )

    result = await materializer.materialize(
        ScDataScope.dataset(dataset_id="dataset-1", org_id="org-1"),
        revision=3,
    )
    second = await materializer.materialize(
        ScDataScope.dataset(dataset_id="dataset-1", org_id="org-1"),
        revision=3,
    )

    assert result.samples_base is samples_base
    assert result.review_images is review_images
    assert second.samples_base is samples_base
    storage.list_samples.assert_not_awaited()
    upstream_reader.list_review_images.assert_not_awaited()


@pytest.mark.asyncio
async def test_dataset_overlays_track_the_monotonic_scope_revision(
    tmp_path: Path,
) -> None:
    storage = AsyncMock()
    storage.get_dataset_metadata.return_value = SimpleNamespace(
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        }
    )
    storage.annotation_overlay_lazyframe.return_value = (
        pl.DataFrame({"sample_id": ["1"], "label": ["A"]}).lazy(),
        "1" * 64,
    )
    storage.prediction_overlay_lazyframe.return_value = (
        pl.DataFrame(
            {
                "sample_id": ["1"],
                "predicted_label": ["A"],
                "confidence": [0.9],
            }
        ).lazy(),
        "2" * 64,
    )
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.return_value = storage
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.return_value = _inspection(1)
    cache = AsyncMock(spec=ScDataObjectCache)
    cache.get_or_build.return_value = _cached_object(
        tmp_path / "review.parquet", "review"
    )
    cache.get_or_build_file.return_value = _cached_object(
        tmp_path / "samples.parquet", "samples"
    )
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        artifact_storage=AsyncMock(spec=ArtifactStorage),
        cache=cache,
        batch_rows=50_000,
        classify_max_rows=300_000,
    )

    await materializer.materialize(
        ScDataScope.dataset(dataset_id="dataset-1", org_id="org-1"),
        revision=7,
    )

    overlay_calls = [
        call.kwargs
        for call in cache.get_or_build_file.await_args_list
        if call.kwargs["logical_key"].endswith((":annotations", ":predictions"))
    ]
    assert len(overlay_calls) == 2
    assert {call["scope_revision"] for call in overlay_calls} == {7}
    storage.list_samples.assert_not_awaited()


@pytest.mark.asyncio
async def test_dataset_materialization_projects_membership_and_reads_latest_source(
    tmp_path: Path,
) -> None:
    storage = AsyncMock()
    storage.get_dataset_metadata.return_value = SimpleNamespace(
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        }
    )
    storage.list_samples.return_value = pl.DataFrame(
        {
            "sample_id": ["42"],
            "defect_id": [42],
            "rough_bin": [1],
            "obsolete_source_field": ["ignored"],
        }
    ).lazy()
    storage.annotation_overlay_lazyframe.return_value = (None, "0" * 64)
    storage.prediction_overlay_lazyframe.return_value = (None, "0" * 64)
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.return_value = storage
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.return_value = _inspection(1, latest_update=2)
    upstream_reader.get_sample_count.return_value = 1

    async def stream_samples(*_args: object, **_kwargs: object):
        yield pa.RecordBatch.from_pylist(
            [
                {
                    "defect_id": 42,
                    "rough_bin": 9,
                    "future_source_field": "latest",
                }
            ]
        )

    upstream_reader.stream_sample_batches.side_effect = stream_samples
    upstream_reader.list_review_images.return_value = pl.DataFrame(
        {"defect_id": [42], "image_id": [100]}
    ).lazy()
    cache = AsyncMock(spec=ScDataObjectCache)
    object_count = 0

    async def get_or_build_file(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        path = tmp_path / f"dataset-file-{object_count}.parquet"
        await kwargs["builder"](path)
        return _cached_object(path, f"file-{object_count}")

    async def get_or_build(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        path = tmp_path / f"dataset-table-{object_count}.parquet"
        pq.write_table(await kwargs["builder"](), path)
        return _cached_object(path, f"table-{object_count}")

    cache.get_or_build_file.side_effect = get_or_build_file
    cache.get_or_build.side_effect = get_or_build
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        artifact_storage=AsyncMock(spec=ArtifactStorage),
        cache=cache,
        batch_rows=50_000,
        classify_max_rows=300_000,
    )

    result = await materializer.materialize(
        ScDataScope.dataset(dataset_id="dataset-1", org_id="org-1"),
        revision=3,
    )

    samples = pl.read_parquet(result.samples_base.path)
    assert samples["sample_id"].to_list() == ["42"]
    assert samples["rough_bin"].to_list() == [9]
    assert samples["future_source_field"].to_list() == ["latest"]
    assert "obsolete_source_field" not in samples.columns
    source_keys = [
        call.kwargs["logical_key"]
        for call in cache.get_or_build_file.await_args_list
        if ":samples-base:" in call.kwargs["logical_key"]
    ]
    assert source_keys == [
        "dataset:org-1/dataset-1:samples-base:v7-latest-source:source-2"
    ]


@pytest.mark.asyncio
async def test_collection_revision_materializes_combined_rows_and_overlays(
    tmp_path: Path,
) -> None:
    revision_path = tmp_path / "revision.parquet"
    pl.DataFrame(
        {
            "row_key": ["dataset-a::sample-1", "dataset-b::sample-9"],
            "sample_id": ["dataset-a::sample-1", "dataset-b::sample-9"],
            "source_dataset_id": ["dataset-a", "dataset-b"],
            "source_sample_id": ["sample-1", "sample-9"],
            "collection_member_id": ["member-a", "member-b"],
            "defect_id": [42, 42],
            "inspection_time": ["2026-08-01T04:00:00+08:00"] * 2,
            "wafer_key": [1, 2],
        }
    ).write_parquet(revision_path)

    storages: dict[str, AsyncMock] = {}
    for dataset_id, wafer_key, sample_id in (
        ("dataset-a", 1, "sample-1"),
        ("dataset-b", 2, "sample-9"),
    ):
        storage = AsyncMock()
        storage.get_dataset_metadata.return_value = SimpleNamespace(
            dataset_meta={
                "source_inspection_time": "2026-08-01T04:00:00+08:00",
                "source_wafer_key": wafer_key,
            }
        )
        storage.annotation_overlay_lazyframe.return_value = (
            pl.DataFrame({"sample_id": [sample_id], "label": [dataset_id]}).lazy(),
            str(wafer_key) * 64,
        )
        storage.prediction_overlay_lazyframe.return_value = (None, "0" * 64)
        storages[dataset_id] = storage

    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.side_effect = lambda dataset_id, _org_id: storages[dataset_id]
    revision_reader = AsyncMock(spec=DatasetCollectionRevisionReaderPort)
    revision_reader.get_revision.return_value = _ready_revision("memory://revision")
    artifact_storage = AsyncMock(spec=ArtifactStorage)

    async def get_file(_uri: str, destination: str) -> None:
        await asyncio.to_thread(shutil.copyfile, revision_path, destination)

    artifact_storage.get_file.side_effect = get_file
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.side_effect = lambda _time, wafer_key: _inspection(
        wafer_key
    )
    upstream_reader.get_sample_count.return_value = 1

    async def stream_samples(
        _time: datetime,
        wafer_key: int,
        **_kwargs: object,
    ):
        yield pa.RecordBatch.from_pylist(
            [
                {
                    "defect_id": 42,
                    "inspection_time": "2026-08-01T04:00:00+08:00",
                    "wafer_key": wafer_key,
                    "wafer_x": wafer_key * 10,
                    "rough_bin": wafer_key,
                }
            ]
        )

    upstream_reader.stream_sample_batches.side_effect = stream_samples
    upstream_reader.list_review_images.side_effect = lambda _time, wafer_key: (
        pl.DataFrame({"defect_id": [42], "image_id": [wafer_key * 100]}).lazy()
    )
    cache = AsyncMock(spec=ScDataObjectCache)
    object_count = 0

    async def get_or_build_file(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        object_id = object_count
        path = tmp_path / f"cache-file-{object_id}.parquet"
        await kwargs["builder"](path)
        return _cached_object(path, f"file-{object_id}")

    async def get_or_build(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        object_id = object_count
        path = tmp_path / f"cache-table-{object_id}.parquet"
        table = await kwargs["builder"]()
        pq.write_table(table, path)
        return _cached_object(path, f"table-{object_id}")

    cache.get_or_build_file.side_effect = get_or_build_file
    cache.get_or_build.side_effect = get_or_build
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=revision_reader,
        artifact_storage=artifact_storage,
        cache=cache,
        batch_rows=50_000,
        classify_max_rows=300_000,
    )

    result = await materializer.materialize(
        ScDataScope.collection(
            collection_id="collection-1",
            revision_id="revision-1",
            org_id="org-1",
        ),
        revision=5,
    )

    samples = pl.read_parquet(result.samples_base.path).sort("map_id")
    assert samples["row_key"].to_list() == [
        "dataset-a::sample-1",
        "dataset-b::sample-9",
    ]
    assert samples["map_id"].to_list() == [0, 1]
    assert samples["review_image_ids_json"].to_list() == ["[100]", "[200]"]
    reviews = pl.read_parquet(result.review_images.path).sort("row_key")
    assert reviews["row_key"].to_list() == [
        "dataset-a::sample-1",
        "dataset-b::sample-9",
    ]
    assert result.annotation_overlay is not None
    annotations = pl.read_parquet(result.annotation_overlay.path).sort("row_key")
    assert annotations["row_key"].to_list() == [
        "dataset-a::sample-1",
        "dataset-b::sample-9",
    ]
