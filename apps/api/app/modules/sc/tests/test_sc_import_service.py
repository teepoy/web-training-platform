from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from app.modules.sc.domain.models import ScInspectionRecord


class _MockRepository:
    def __init__(self) -> None:
        self.updated_meta: dict | None = None

    async def create_dataset(self, dataset, org_id: str | None = None):
        return dataset.model_copy(update={"org_id": org_id})

    async def update_dataset_meta(
        self,
        dataset_id: str,
        meta_update: dict,
        *,
        org_id: str | None = None,
    ) -> None:
        self.updated_meta = meta_update


class _MockPayloadStore:
    def __init__(self) -> None:
        self.manifest = None
        self.shards = []
        self.index = b""

    async def put_manifest(self, manifest, *, org_id: str) -> str:
        self.manifest = manifest
        return f"memory://datasets/{org_id}/{manifest.dataset_id}/manifest.json"

    async def put_shard(
        self,
        *,
        dataset_id: str,
        org_id: str,
        shard_index: int,
        data: bytes,
        row_count: int,
        format: str = "parquet",
    ):
        from app.modules.storage.domain.sparse import ShardEntry

        self.shards.append(data)
        return ShardEntry(
            shard_index=shard_index,
            uri=f"memory://datasets/{org_id}/{dataset_id}/shards/{shard_index}",
            row_count=row_count,
            format=format,
            checksum_sha256="checksum",
            byte_size=len(data),
        )

    async def put_shard_file(
        self,
        *,
        dataset_id: str,
        org_id: str,
        shard_index: int,
        path: str,
        row_count: int,
        format: str = "parquet",
    ):
        return await self.put_shard(
            dataset_id=dataset_id,
            org_id=org_id,
            shard_index=shard_index,
            data=Path(path).read_bytes(),
            row_count=row_count,
            format=format,
        )

    async def put_index_file(
        self,
        *,
        dataset_id: str,
        org_id: str,
        path: str,
        row_count: int,
    ):
        from app.modules.storage.domain.sparse import SparseIndexEntry

        del dataset_id, org_id
        self.index = Path(path).read_bytes()
        return SparseIndexEntry(
            uri="memory://sample-index.parquet",
            row_count=row_count,
            checksum_sha256="checksum",
            byte_size=len(self.index),
        )

    async def delete_object(self, uri: str) -> None:
        del uri


class _MockUpstream:
    def __init__(self, inspection_return=None, row_count: int = 1000) -> None:
        self._inspection_return = inspection_return
        self._row_count = row_count
        self.list_samples_calls: list[tuple] = []
        self.stream_sample_calls: list[tuple] = []

    async def list_inspections(
        self, start_time, end_time,
        lot_id=None, wafer_id=None, layer_id=None, device=None,
    ):

        return pl.LazyFrame([])

    async def get_inspection(self, inspection_time, wafer_key):
        return self._inspection_return

    async def get_sample_count(self, inspection_time, wafer_key):
        del inspection_time, wafer_key
        return self._row_count

    async def stream_sample_batches(
        self,
        inspection_time,
        wafer_key,
        *,
        offset=0,
        count=None,
        batch_rows,
        projection=None,
        on_progress=None,
    ):
        del projection
        self.stream_sample_calls.append((inspection_time, wafer_key, offset, count, batch_rows))
        stop = self._row_count if count is None else min(offset + count, self._row_count)
        loaded = 0
        for start in range(offset, stop, batch_rows):
            end = min(start + batch_rows, stop)
            rows = [
                {
                    "inspection_time": str(inspection_time),
                    "wafer_key": wafer_key,
                    "defect_id": defect_id,
                    "lot_id": "LOT-001",
                    "wafer_x": defect_id,
                    "wafer_y": defect_id,
                    "die_x": 0,
                    "die_y": 0,
                    "rough_bin": 1,
                    "class_number": 1,
                    "test_id": None,
                }
                for defect_id in range(start + 1, end + 1)
            ]
            table = pl.DataFrame(rows).to_arrow()
            for batch in table.to_batches():
                loaded += batch.num_rows
                if on_progress is not None:
                    on_progress(loaded)
                yield batch

    async def list_samples(
        self,
        inspection_time,
        wafer_key,
        offset=0,
        count=None,
        reticle_size_x=1,
        reticle_size_y=1,
        reticle_offset_x=0,
        reticle_offset_y=0,
        on_progress=None,
    ):

        self.list_samples_calls.append((inspection_time, wafer_key, offset, count))

        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")

        if count == 1:
            # Pre-check mode
            return pl.DataFrame({"defect_id": [1] if self._row_count > 0 else []}).lazy()

        # Full mode (count=None)
        rows = []
        for defect_id in range(1, self._row_count + 1):
            rows.append(
                {
                    "sample_id": str(defect_id),
                    "inspection_time": str(inspection_time),
                    "wafer_key": wafer_key,
                    "defect_id": str(defect_id),
                    "lot_id": "LOT-001",
                    "wafer_x": defect_id,
                    "wafer_y": defect_id,
                    "die_x": 0,
                    "die_y": 0,
                    "rough_bin": 1,
                    "class_number": 1,
                }
            )
        return pl.DataFrame(rows).lazy()

    async def list_review_images(self, inspection_time, wafer_key):

        return pl.LazyFrame([])


def _make_service(upstream_reader=None, repository=None, payload_store=None):
    from app.modules.storage.adapter.sparse.import_operator import (
        SparseImportOperatorFactory,
    )
    from app.modules.sc.app.services.sc_import_service import ScImportService

    return ScImportService(
        sparse_import_factory=SparseImportOperatorFactory(),
        repository=repository or _MockRepository(),
        payload_store=payload_store or _MockPayloadStore(),
        upstream_reader=upstream_reader or _MockUpstream(row_count=1000),
        import_batch_rows=25_000,
        index_row_group_rows=65_536,
    )


@pytest.mark.asyncio
async def test_hybrid_data_exhausted_before_threshold_completes() -> None:
    upstream = _MockUpstream(row_count=20)
    service = _make_service(upstream_reader=upstream)

    status = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid exhausted",
        org_id="test-org",
        max_rows=None,
    )

    assert status.status == "completed"
    assert status.imported_count == 20


@pytest.mark.asyncio
async def test_boundary_exact_30k_stays_direct_only() -> None:
    upstream = _MockUpstream(row_count=30_005)
    service = _make_service(upstream_reader=upstream)

    status = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Direct boundary",
        org_id="test-org",
        max_rows=30_000,
    )

    assert status.status == "completed"
    assert status.imported_count == 30_000


@pytest.mark.asyncio
async def test_direct_import_persists_geometry_metadata() -> None:
    """Direct (sync) import should persist wafer geometry in dataset_meta."""

    mock_inspection = ScInspectionRecord(
        inspection_time=datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc),
        wafer_key=1,
        lot_id="LOT-001",
        wafer_id="W-001",
        center_x=500,
        center_y=500,
        origin_x=0,
        origin_y=0,
        die_size_x=100,
        die_size_y=100,
        device="DEVICE-A",
        origin_index_x=0,
        origin_index_y=0,
        defects=100,
        images=4,
    )

    upstream = _MockUpstream(inspection_return=mock_inspection)
    repo = _MockRepository()

    service = _make_service(upstream_reader=upstream, repository=repo)

    await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Geometry Test Dataset",
        org_id="test-org",
        max_rows=100,
    )

    assert repo.updated_meta is not None
    assert "geometry" in repo.updated_meta
    geometry = repo.updated_meta["geometry"]

    expected_keys = {
        "center_x", "center_y", "origin_x", "origin_y",
        "die_size_x", "die_size_y", "origin_index_x", "origin_index_y",
        "wafer_id", "lot_id", "device",
    }
    assert set(geometry.keys()) == expected_keys, (
        f"Expected {expected_keys}, got {set(geometry.keys())}"
    )

    assert geometry["center_x"] == 500
    assert geometry["center_y"] == 500
    assert geometry["die_size_x"] == 100
    assert geometry["die_size_y"] == 100
    assert geometry["lot_id"] == "LOT-001"
    assert geometry["wafer_id"] == "W-001"
    assert geometry["device"] == "DEVICE-A"


@pytest.mark.asyncio
async def test_hybrid_shuffle_exhausted_early() -> None:
    upstream = _MockUpstream(row_count=1000)
    service = _make_service(upstream_reader=upstream)

    status = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid shuffle exhausted",
        org_id="test-org",
        max_rows=50_000,
    )

    assert status.status == "completed"


@pytest.mark.asyncio
async def test_direct_import_uses_shuffled_ids() -> None:
    payload_store = _MockPayloadStore()
    upstream = _MockUpstream(row_count=100)
    service = _make_service(upstream_reader=upstream, payload_store=payload_store)

    status = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Shuffle direct",
        org_id="test-org",
        max_rows=50,
    )

    assert status.status == "completed"
    assert upstream.list_samples_calls == []
    assert len(upstream.stream_sample_calls) == 1
    stream_time, stream_wafer, stream_offset, stream_count, stream_batch = (
        upstream.stream_sample_calls[0]
    )
    assert stream_time.isoformat().startswith("2024-01-15T08:30:00")
    assert (stream_wafer, stream_offset, stream_count, stream_batch) == (
        1,
        0,
        50,
        25_000,
    )
    assert payload_store.manifest is not None
    assert payload_store.manifest.total_rows == 50
    assert payload_store.manifest.manifest_version == "v3"
    assert payload_store.manifest.sample_index == {}
    assert payload_store.manifest.index is not None


@pytest.mark.asyncio
async def test_direct_import_shuffle_reproducible() -> None:
    payload_store_a = _MockPayloadStore()
    upstream_a = _MockUpstream(row_count=100)
    service_a = _make_service(upstream_reader=upstream_a, payload_store=payload_store_a)
    await service_a.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Reproducible A",
        org_id="test-org",
        max_rows=50,
    )

    payload_store_b = _MockPayloadStore()
    upstream_b = _MockUpstream(row_count=100)
    service_b = _make_service(upstream_reader=upstream_b, payload_store=payload_store_b)
    await service_b.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Reproducible B",
        org_id="test-org",
        max_rows=50,
    )

    assert payload_store_a.manifest is not None
    assert payload_store_b.manifest is not None
    assert payload_store_a.manifest.total_rows == payload_store_b.manifest.total_rows
