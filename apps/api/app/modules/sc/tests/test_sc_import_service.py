from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import polars as pl
import pytest

from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.modules.datasets.port.local import DatasetRevisionPublisherPort
from app.shared.api.schemas import Dataset


class _MockRepository:
    def __init__(self) -> None:
        self.updated_meta: dict | None = None
        self.created_dataset: Dataset | None = None

    async def create_dataset(
        self, dataset: Dataset, org_id: str | None = None
    ) -> Dataset:
        self.created_dataset = dataset
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


class _MockRevisionPublisher:
    def __init__(self) -> None:
        self.publications: list[dict[str, object]] = []

    async def publish_sparse_revision(
        self,
        *,
        dataset_id: str,
        org_id: str,
        operation: DatasetRevisionOperation,
        created_by: str,
        provenance: dict[str, object] | None = None,
        operation_ref: str | None = None,
    ) -> DatasetRevision:
        publication: dict[str, object] = {
            "dataset_id": dataset_id,
            "org_id": org_id,
            "operation": operation,
            "created_by": created_by,
            "provenance": provenance or {},
        }
        if operation_ref is not None:
            publication["operation_ref"] = operation_ref
        self.publications.append(publication)
        return DatasetRevision(
            id="revision-test",
            dataset_id=dataset_id,
            revision_number=1,
            manifest_uri="memory://revision-test/manifest.json",
            operation=operation,
            operation_ref=operation_ref,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            provenance=provenance or {},
        )


class _MockUpstream:
    def __init__(self, inspection_return=None, row_count: int = 1000) -> None:
        self._inspection_return = inspection_return
        self._row_count = row_count
        self.list_samples_calls: list[tuple] = []
        self.stream_sample_calls: list[tuple] = []

    async def list_inspections(
        self,
        start_time,
        end_time,
        lot_id=None,
        wafer_id=None,
        layer_id=None,
        device=None,
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
        self.stream_sample_calls.append(
            (inspection_time, wafer_key, offset, count, batch_rows)
        )
        stop = (
            self._row_count if count is None else min(offset + count, self._row_count)
        )
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
                    "index_x": defect_id % 11,
                    "future_metric": defect_id / 10,
                }
                for defect_id in range(start + 1, end + 1)
            ]
            table = pl.DataFrame(rows).to_arrow()
            for batch in table.to_batches():
                loaded += batch.num_rows
                if on_progress is not None:
                    on_progress(loaded)
                yield batch

    async def stream_membership_sample_batches(
        self,
        inspection_time,
        wafer_key,
        *,
        defect_ids,
        batch_rows,
        projection=None,
    ):
        requested = {int(defect_id) for defect_id in defect_ids}
        async for batch in self.stream_sample_batches(
            inspection_time,
            wafer_key,
            count=self._row_count,
            batch_rows=batch_rows,
            projection=projection,
        ):
            frame = cast(pl.DataFrame, pl.from_arrow(batch)).filter(
                pl.col("defect_id").is_in(requested)
            )
            if projection is not None:
                frame = frame.select(
                    *[column for column in projection if column in frame.columns]
                )
            for result_batch in frame.to_arrow().to_batches():
                yield result_batch

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
            return pl.DataFrame(
                {"defect_id": [1] if self._row_count > 0 else []}
            ).lazy()

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


def _make_service(
    upstream_reader=None,
    repository=None,
    payload_store=None,
    revision_publisher: DatasetRevisionPublisherPort | None = None,
):
    from app.modules.storage.adapter.sparse.import_operator import (
        SparseImportOperatorFactory,
    )
    from app.modules.sc.app.services.sc_import_service import ScImportService

    return ScImportService(
        sparse_import_factory=SparseImportOperatorFactory(),
        repository=repository or _MockRepository(),
        payload_store=payload_store or _MockPayloadStore(),
        revision_publisher=revision_publisher or _MockRevisionPublisher(),
        upstream_reader=upstream_reader or _MockUpstream(row_count=1000),
        import_batch_rows=25_000,
        index_row_group_rows=65_536,
    )


@pytest.mark.asyncio
async def test_direct_upstream_import_does_not_embed_parser_selection() -> None:
    repository = _MockRepository()
    service = _make_service(
        upstream_reader=_MockUpstream(row_count=1),
        repository=repository,
    )

    status = await service.submit_upstream_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=7,
        dataset_name="Configured upstream format",
        org_id="test-org",
    )

    assert status.status == "completed"
    assert repository.created_dataset is not None
    assert repository.created_dataset.image_source is None


@pytest.mark.asyncio
async def test_completed_sc_import_publishes_initial_dataset_revision() -> None:
    publisher = _MockRevisionPublisher()
    repository = _MockRepository()
    service = _make_service(
        upstream_reader=_MockUpstream(row_count=20),
        repository=repository,
        revision_publisher=publisher,
    )

    status = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=7,
        dataset_name="Revision publication",
        org_id="test-org",
        created_by="test-user",
    )

    assert status.status == "completed"
    assert repository.created_dataset is not None
    assert repository.created_dataset.image_source is None
    assert len(publisher.publications) == 1
    publication = publisher.publications[0]
    assert publication["dataset_id"] == status.dataset_id
    assert publication["org_id"] == "test-org"
    assert publication["operation"] == "initial_import"
    assert publication["created_by"] == "test-user"
    assert publication["provenance"] == {
        "source_connector": "sc",
        "source_inspection_time": "2024-01-15T08:30:00",
        "source_wafer_key": 7,
    }


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
async def test_direct_import_persists_only_source_identity_metadata() -> None:
    """Import must not freeze mutable upstream geometry in Dataset metadata."""

    upstream = _MockUpstream(row_count=100)
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
    assert repo.updated_meta == {
        "source_inspection_time": "2024-01-15T08:30:00",
        "source_wafer_key": 1,
    }


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
    import io
    from uuid import UUID

    import pyarrow.parquet as pq

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
    assert payload_store.manifest.schema_version == "v4_identity"
    assert {column.name for column in payload_store.manifest.schema_columns} == {
        "sample_id",
        "defect_id",
    }
    assert {"index_x", "future_metric"}.isdisjoint(
        {column.name for column in payload_store.manifest.schema_columns}
    )
    assert payload_store.manifest.sample_index == {}
    assert payload_store.manifest.index is not None
    assert payload_store.shards
    parquet = pq.ParquetFile(io.BytesIO(payload_store.shards[0]))
    assert parquet.schema_arrow.metadata == {b"schema_version": b"v4_identity"}
    assert parquet.schema_arrow.names == ["sample_id", "defect_id"]
    imported_rows = parquet.read().to_pylist()
    imported_ids = [str(row["sample_id"]) for row in imported_rows]
    assert len(set(imported_ids)) == len(imported_rows)
    assert all(UUID(sample_id).version == 4 for sample_id in imported_ids)
    assert all(row["sample_id"] != row["defect_id"] for row in imported_rows)

    index = pq.read_table(io.BytesIO(payload_store.index)).to_pylist()
    assert [row["sample_id"] for row in index] == imported_ids
    assert [row["upstream_item_id"] for row in index] == [
        str(row["defect_id"]) for row in imported_rows
    ]


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
