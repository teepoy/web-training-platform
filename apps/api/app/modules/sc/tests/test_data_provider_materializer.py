from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import polars as pl
import pytest

from app.modules.sc.data_provider.cache import CachedDataObject, ScDataObjectCache
from app.modules.sc.data_provider.materializer import ScDataMaterializer
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.storage.port.local import DatasetStorageFactoryPort


def _cached_object(path: Path, object_id: str) -> CachedDataObject:
    return CachedDataObject(
        object_id=object_id,
        path=path,
        size_bytes=1,
        scope="org:org-1:dataset:dataset-1",
        revision=0,
        cache_status="hit",
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
    cache = AsyncMock(spec=ScDataObjectCache)
    review_images = _cached_object(tmp_path / "review.parquet", "review")
    samples_base = _cached_object(tmp_path / "samples.parquet", "samples")
    cache.get_or_build.return_value = review_images
    cache.get_or_build_file.return_value = samples_base
    materializer = ScDataMaterializer(
        upstream_reader=upstream_reader,
        storage_factory=storage_factory,
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
