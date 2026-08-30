from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.core.config import load_config
from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.dataset_collections.port.local import (
    DatasetCollectionRevisionReaderPort,
)
from app.modules.sc.data_provider.cache import CachedDataObject, ScDataObjectCache
from app.modules.sc.data_provider.engine import DuckDbQueryExecutor
from app.modules.sc.data_provider.materializer import ScDataMaterializer
from app.modules.sc.data_provider.sampling import compile_sc_sampling_query
from app.modules.sc.data_provider.schemas import (
    ScSamplingSelectionRequest,
    ScSqlParameter,
)
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.data_provider.sql_policy import validate_sc_sql
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.domain.models import ScInspectionRecord
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import DatasetStorageMode


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
        members=(
            {"member_id": "member-a", "source_dataset_id": "dataset-a"},
            {"member_id": "member-b", "source_dataset_id": "dataset-b"},
        ),
        manifest_uri=manifest_uri,
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=datetime.now(timezone.utc),
        error_code=None,
        error_detail=None,
    )


def _inspection(
    wafer_key: int,
    *,
    latest_update: int = 1,
    change_token: int = 101,
) -> ScInspectionRecord:
    return ScInspectionRecord(
        inspection_time=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
        wafer_key=wafer_key,
        device=f"device-{wafer_key}",
        latest_update=latest_update,
        change_token=change_token,
    )


@pytest.mark.asyncio
async def test_collection_materialization_has_no_browser_row_count_guard() -> None:
    revision_reader = AsyncMock(spec=DatasetCollectionRevisionReaderPort)
    revision_reader.get_revision.return_value = _ready_revision("memory://revision")
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.side_effect = RuntimeError("continued to current datasets")
    materializer = ScDataMaterializer(
        upstream_reader=AsyncMock(spec=ScUpstreamReader),
        storage_factory=storage_factory,
        collection_revision_reader=revision_reader,
        cache=AsyncMock(spec=ScDataObjectCache),
        batch_rows=50_000,
    )

    with pytest.raises(RuntimeError, match="continued to current datasets"):
        await materializer.materialize(
            ScDataScope.collection(
                collection_id="collection-1",
                revision_id="revision-1",
                org_id="org-1",
            ),
            revision=1,
        )

    storage_factory.open.assert_awaited()


@pytest.mark.asyncio
async def test_inspection_source_caches_use_authoritative_change_token(
    tmp_path: Path,
) -> None:
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.return_value = _inspection(
        1,
        latest_update=7,
        change_token=701,
    )
    upstream_reader.get_sample_count.return_value = 0
    upstream_reader.list_review_images.return_value = pl.DataFrame(
        {"defect_id": pl.Series([], dtype=pl.Int32), "image_id": pl.Series([], dtype=pl.Int64)}
    ).lazy()
    cache = AsyncMock(spec=ScDataObjectCache)
    cache.get_or_build_file.return_value = _cached_object(
        tmp_path / "samples.parquet", "samples"
    )

    async def get_or_build(**kwargs) -> CachedDataObject:
        await kwargs["builder"]()
        return _cached_object(tmp_path / "reviews.parquet", "reviews")

    cache.get_or_build.side_effect = get_or_build
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=AsyncMock(spec=DatasetStorageFactoryPort),
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        cache=cache,
        batch_rows=50_000,
    )

    await materializer.materialize(
        ScDataScope.inspection(
            inspection_time="2026-08-01T04:00:00+00:00",
            wafer_key=1,
            org_id="org-1",
        ),
        revision=0,
    )

    source_keys = {
        cache.get_or_build_file.await_args.kwargs["logical_key"],
        cache.get_or_build.await_args.kwargs["logical_key"],
    }
    assert all(key.endswith("source-701") for key in source_keys)


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
        cache=cache,
        batch_rows=50_000,
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
async def test_db_full_dataset_materializes_persisted_sc_rows_without_source_scope(
    tmp_path: Path,
) -> None:
    storage = AsyncMock()
    storage.storage_mode = DatasetStorageMode.DB_FULL
    storage.get_dataset_metadata.return_value = SimpleNamespace(dataset_meta={})
    storage.list_samples.return_value = pl.DataFrame(
        {
            "id": ["platform-sample-42"],
            "dataset_id": ["dataset-1"],
            "image_uris": [[]],
            "metadata_json": [
                {
                    "sample_id": "upstream-sample-42",
                    "inspection_time": "2026-08-09T10:36:46+00:00",
                    "wafer_key": 0,
                    "defect_id": 42,
                    "wafer_x": 100,
                    "wafer_y": 200,
                    "rough_bin": 1,
                    "class_number": 2,
                    "shard_images": [{"role": "patch_defective"}],
                }
            ],
            "ls_task_id": [None],
            "created_at": [datetime(2026, 8, 9, tzinfo=timezone.utc)],
        }
    ).lazy()
    storage.annotation_overlay_lazyframe.return_value = (None, "0" * 64)
    storage.prediction_overlay_lazyframe.return_value = (None, "0" * 64)
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.return_value = storage
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    cache = AsyncMock(spec=ScDataObjectCache)
    object_count = 0

    async def get_or_build_file(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        path = tmp_path / f"persisted-file-{object_count}.parquet"
        await kwargs["builder"](path)
        return _cached_object(path, f"file-{object_count}")

    async def get_or_build(**kwargs) -> CachedDataObject:
        nonlocal object_count
        object_count += 1
        path = tmp_path / f"persisted-table-{object_count}.parquet"
        pq.write_table(await kwargs["builder"](), path)
        return _cached_object(path, f"table-{object_count}")

    cache.get_or_build_file.side_effect = get_or_build_file
    cache.get_or_build.side_effect = get_or_build
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        cache=cache,
        batch_rows=50_000,
    )

    result = await materializer.materialize(
        ScDataScope.dataset(dataset_id="dataset-1", org_id="org-1"),
        revision=3,
    )

    samples = pl.read_parquet(result.samples_base.path)
    assert samples["row_key"].to_list() == ["platform-sample-42"]
    assert samples["source_sample_id"].to_list() == ["upstream-sample-42"]
    assert samples["defect_id"].to_list() == [42]
    assert samples["map_id"].to_list() == [0]
    assert "shard_images" not in samples.columns
    upstream_reader.get_inspection.assert_not_awaited()
    upstream_reader.list_review_images.assert_not_awaited()

    config = load_config(skip_runtime_validation=True).sc.data_provider.model_copy(
        update={"cache_dir": str(tmp_path)}
    )
    executor = DuckDbQueryExecutor(config=config)

    async def query(sql: str, parameters: list[ScSqlParameter]) -> pa.Table:
        prepared = await executor.prepare_stream(
            sql=validate_sc_sql(sql),
            parameters=parameters,
            materialized=result,
        )
        payload = b"".join([chunk async for chunk in prepared.body])
        return pa.ipc.open_stream(payload).read_all()

    try:
        filter_statistics = await query(
            "SELECT MIN(wafer_x) AS min_x, MAX(wafer_x) AS max_x, "
            "COUNT(*) AS row_count FROM samples",
            [],
        )
        assert filter_statistics.to_pydict() == {
            "min_x": [100],
            "max_x": [100],
            "row_count": [1],
        }

        sampling_preparation = await query(
            "SELECT wafer_key AS group_key, COUNT(*) AS group_count "
            "FROM samples WHERE final_class NOT IN (?) "
            "AND final_class IS NOT NULL GROUP BY wafer_key ORDER BY wafer_key",
            [""],
        )
        assert sampling_preparation.num_rows == 0

        sampling = ScSamplingSelectionRequest.model_validate(
            {
                "seed": 42,
                "program": {"rules": [{"type": "random_count", "count": 1}]},
            }
        )
        sampling_sql, sampling_parameters = compile_sc_sampling_query(
            validate_sc_sql("SELECT map_id FROM samples"),
            [],
            sampling,
        )
        prepared_sampling = await executor.prepare_stream(
            sql=sampling_sql,
            parameters=sampling_parameters,
            materialized=result,
        )
        sampling_payload = b"".join(
            [chunk async for chunk in prepared_sampling.body]
        )
        assert pa.ipc.open_stream(sampling_payload).read_all().to_pydict() == {
            "defect_id": [0]
        }

        map_rows = await query(
            "SELECT map_id, row_key, wafer_x, wafer_y, die_x, die_y, "
            "rough_bin, images FROM samples ORDER BY map_id",
            [],
        )
        assert map_rows.to_pydict() == {
            "map_id": [0],
            "row_key": ["platform-sample-42"],
            "wafer_x": [100],
            "wafer_y": [200],
            "die_x": [None],
            "die_y": [None],
            "rough_bin": [1],
            "images": [0],
        }
    finally:
        await executor.close()


@pytest.mark.asyncio
async def test_sparse_dataset_reports_missing_upstream_inspection_as_not_found() -> None:
    storage = AsyncMock()
    storage.storage_mode = DatasetStorageMode.FILE_SHARD_SPARSE
    storage.get_dataset_metadata.return_value = SimpleNamespace(
        dataset_meta={
            "source_inspection_time": "2026-08-01T04:00:00+08:00",
            "source_wafer_key": 1,
        }
    )
    storage_factory = AsyncMock(spec=DatasetStorageFactoryPort)
    storage_factory.open.return_value = storage
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.return_value = None
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
        collection_revision_reader=AsyncMock(spec=DatasetCollectionRevisionReaderPort),
        cache=AsyncMock(spec=ScDataObjectCache),
        batch_rows=50_000,
    )

    with pytest.raises(
        ValueError,
        match=r"Inspection not found: 2026-08-01T04:00:00\+08:00/1",
    ):
        await materializer.materialize(
            ScDataScope.dataset(
                dataset_id="fefd5b68-bb47-4679-bd74-73b80e5a5176",
                org_id="org-1",
            ),
            revision=1,
        )

    storage.list_samples.assert_not_awaited()


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
        cache=cache,
        batch_rows=50_000,
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
    upstream_reader.get_inspection.return_value = _inspection(
        1,
        latest_update=2,
        change_token=702,
    )
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

    upstream_reader.stream_membership_sample_batches.side_effect = stream_samples
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
        cache=cache,
        batch_rows=50_000,
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
        "dataset:org-1/dataset-1:samples-base:v7-latest-source:source-702"
    ]
    review_keys = [
        call.kwargs["logical_key"]
        for call in cache.get_or_build.await_args_list
        if ":review-images:" in call.kwargs["logical_key"]
    ]
    assert review_keys == [
        "inspection:2026-08-01T04:00:00+08:00/1:review-images:"
        "v2-row-key:source-702"
    ]


@pytest.mark.asyncio
async def test_collection_revision_materializes_combined_rows_and_overlays(
    tmp_path: Path,
) -> None:
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
        storage.list_samples.return_value = pl.DataFrame(
            {"sample_id": [sample_id], "defect_id": [42]}
        ).lazy()
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
    upstream_reader = AsyncMock(spec=ScUpstreamReader)
    upstream_reader.get_inspection.side_effect = lambda _time, wafer_key: _inspection(
        wafer_key,
        latest_update=wafer_key,
        change_token=200 + wafer_key,
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

    upstream_reader.stream_membership_sample_batches.side_effect = stream_samples
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
        cache=cache,
        batch_rows=50_000,
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
    source_keys = {
        call.kwargs["logical_key"]
        for call in (
            *cache.get_or_build_file.await_args_list,
            *cache.get_or_build.await_args_list,
        )
        if ":samples-base:" in call.kwargs["logical_key"]
        or ":review-images:" in call.kwargs["logical_key"]
    }
    assert len(source_keys) == 2
    assert all(key.endswith("source-e60cfb7968e67431") for key in source_keys)
