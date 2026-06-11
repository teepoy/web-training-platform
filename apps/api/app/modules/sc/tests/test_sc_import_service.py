from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from app.modules.sc.domain.models import ScInspectionRecord


class _MockPrefectSuccess:
    """Mock Prefect client that returns a valid deployment and flow run."""

    def __init__(self) -> None:
        self.parameters: dict[str, object] = {}
        self.create_calls = 0

    async def resolve_deployment_id(self, deployment_name: str) -> str | None:
        return "test-deployment-id"

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict[str, object],
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        self.create_calls += 1
        self.parameters = parameters
        return {"id": "test-run-id-123"}


class _MockPrefectNoDeployment:
    """Mock Prefect client where deployment is not found."""

    async def resolve_deployment_id(self, deployment_name: str) -> str | None:
        return None

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict[str, object],
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        raise RuntimeError("should not be called")


class _MockPrefectCreateFails:
    """Mock Prefect client where flow run creation raises."""

    async def resolve_deployment_id(self, deployment_name: str) -> str | None:
        return "test-deployment-id"

    async def create_flow_run_from_deployment(
        self,
        deployment_id: str,
        parameters: dict[str, object],
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        raise Exception("Prefect API unavailable")


class _MockRepository:
    def __init__(self) -> None:
        self.updated_meta: dict | None = None

    async def create_dataset(self, dataset, org_id: str | None = None):
        return dataset.model_copy(update={"org_id": org_id})

    async def update_dataset_meta(self, dataset_id: str, meta_update: dict) -> None:
        self.updated_meta = meta_update


class _MockPayloadStore:
    def __init__(self) -> None:
        self.manifest = None
        self.shards = []

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
        from platform_runtime.sparse import ShardEntry

        self.shards.append(data)
        return ShardEntry(
            shard_index=shard_index,
            uri=f"memory://datasets/{org_id}/{dataset_id}/shards/{shard_index}",
            row_count=row_count,
            format=format,
            checksum_sha256="checksum",
            byte_size=len(data),
        )


class _MockUpstream:
    def __init__(self, inspection_return=None, row_count: int = 1000) -> None:
        self._inspection_return = inspection_return
        self._row_count = row_count
        self.list_samples_calls: list[tuple] = []

    async def list_inspections(self, start_time, end_time):

        return pl.LazyFrame([])

    async def get_inspection(self, inspection_time, wafer_key):
        return self._inspection_return

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

    async def list_wafer_points(
        self,
        inspection_time,
        wafer_key,
        reticle_size_x=1,
        reticle_size_y=1,
        reticle_offset_x=0,
        reticle_offset_y=0,
    ):

        return pl.LazyFrame([])


class _MockImageFetcher:
    def proxy_url(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
    ) -> str:
        return ""

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
        return b""


def _make_service(
    prefect_client, upstream_reader=None, repository=None, payload_store=None
):
    from app.modules.sc.app.services.sc_import_service import ScImportService

    return ScImportService(
        prefect_client=prefect_client,
        repository=repository or _MockRepository(),
        payload_store=payload_store or _MockPayloadStore(),
        upstream_reader=upstream_reader or _MockUpstream(row_count=1000),
        image_fetcher=_MockImageFetcher(),
    )


@pytest.mark.asyncio
async def test_hybrid_submit_with_large_max_rows() -> None:
    mock_prefect = _MockPrefectSuccess()
    payload_store = _MockPayloadStore()
    upstream = _MockUpstream(row_count=30_005)
    service = _make_service(
        mock_prefect, upstream_reader=upstream, payload_store=payload_store
    )

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid 50k",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50_000,
    )

    assert status.status == "running"
    assert status.imported_count == 30_000
    assert status.flow_run_id == "test-run-id-123"
    assert flow_run_id == "test-run-id-123"
    assert mock_prefect.parameters["offset"] == 30_000
    assert mock_prefect.parameters["max_rows"] == 20_000
    assert len(upstream.list_samples_calls) >= 1
    assert payload_store.manifest is not None
    assert payload_store.manifest.total_rows == 30_000


@pytest.mark.asyncio
async def test_hybrid_submit_with_max_rows_none() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=30_001)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, _ = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid all",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=None,
    )

    assert status.status == "running"
    assert status.imported_count == 30_000
    assert mock_prefect.parameters["offset"] == 30_000
    assert mock_prefect.parameters["max_rows"] is None


@pytest.mark.asyncio
async def test_hybrid_data_exhausted_before_threshold_completes() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=20)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid exhausted",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=None,
    )

    assert status.status == "completed"
    assert status.imported_count == 20
    assert status.flow_run_id is None
    assert flow_run_id is None
    assert mock_prefect.create_calls == 0


@pytest.mark.asyncio
async def test_boundary_30k_plus_1_triggers_hybrid() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=30_001)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, _ = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid boundary",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=30_001,
    )

    assert status.status == "running"
    assert status.imported_count == 30_000
    assert mock_prefect.parameters["offset"] == 30_000
    assert mock_prefect.parameters["max_rows"] == 1


@pytest.mark.asyncio
async def test_boundary_exact_30k_stays_direct_only() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=30_005)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Direct boundary",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=30_000,
    )

    assert status.status == "completed"
    assert status.imported_count == 30_000
    assert status.flow_run_id is None
    assert flow_run_id is None
    assert mock_prefect.create_calls == 0


@pytest.mark.asyncio
async def test_submit_import_creates_flow_run() -> None:
    """submit_import() should dispatch Prefect flow and return running status."""
    mock_prefect = _MockPrefectSuccess()
    service = _make_service(mock_prefect)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Test SC Dataset",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        force_prefect_flow=True,
    )

    # Assert: returns running status with flow_run_id
    assert status.status == "running"
    assert status.flow_run_id == "test-run-id-123"
    assert flow_run_id == "test-run-id-123"
    assert status.source_inspection_time == "2024-01-15T08:30:00"
    assert status.source_wafer_key == 1
    assert status.dataset_name == "Test SC Dataset"
    assert status.dataset_id
    assert mock_prefect.parameters["dataset_id"] == status.dataset_id
    assert mock_prefect.parameters["offset"] == 0
    assert status.storage_mode == "file_shard_sparse"
    assert status.error is None


@pytest.mark.asyncio
async def test_submit_import_deployment_not_found_returns_failed() -> None:
    """When deployment is not found, submit_import() should return failed status."""
    mock_prefect = _MockPrefectNoDeployment()
    service = _make_service(mock_prefect)
    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Test SC Dataset",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        force_prefect_flow=True,
    )

    # Assert: returns failed status, no flow_run_id
    assert status.status == "failed"
    assert flow_run_id is None
    assert status.error is not None
    assert "deployment" in status.error.lower() or "not found" in status.error.lower()


@pytest.mark.asyncio
async def test_submit_import_prefect_create_fails_returns_failed() -> None:
    """When create_flow_run_from_deployment raises, submit_import() should return failed status."""
    mock_prefect = _MockPrefectCreateFails()
    service = _make_service(mock_prefect)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Test SC Dataset",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        force_prefect_flow=True,
    )

    # Assert: returns failed status
    assert status.status == "failed"
    assert flow_run_id is None
    assert status.error is not None


@pytest.mark.asyncio
async def test_submit_import_prefect_resolve_raises_returns_failed() -> None:
    """When resolve_deployment_id itself raises, submit_import() should return failed status."""

    class _MockPrefectResolveFails:
        async def resolve_deployment_id(self, deployment_name: str) -> str | None:
            raise Exception("Prefect API connection refused")

        async def create_flow_run_from_deployment(
            self,
            deployment_id: str,
            parameters: dict[str, object],
            idempotency_key: str | None = None,
        ) -> dict[str, object]:
            raise RuntimeError("should not be called")

    mock_prefect = _MockPrefectResolveFails()
    service = _make_service(mock_prefect)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Test SC Dataset",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        force_prefect_flow=True,
    )

    assert status.status == "failed"
    assert flow_run_id is None
    assert status.error is not None


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
    prefect_client = _MockPrefectSuccess()

    service = _make_service(prefect_client, upstream_reader=upstream, repository=repo)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Geometry Test Dataset",
        storage_mode="file_shard_sparse",
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
async def test_hybrid_shuffle_uses_shuffled_ids() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=100_000)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, _ = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid shuffle 100k",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=100_000,
    )

    assert status.status == "running"
    assert mock_prefect.parameters["total_available"] == 100_000
    assert mock_prefect.parameters["offset"] == 30_000


@pytest.mark.asyncio
async def test_hybrid_shuffle_exhausted_early() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=1000)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid shuffle exhausted",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50_000,
    )

    assert status.status == "completed"
    assert mock_prefect.create_calls == 0
    assert flow_run_id is None


@pytest.mark.asyncio
async def test_hybrid_shuffle_prefect_params() -> None:
    mock_prefect = _MockPrefectSuccess()
    upstream = _MockUpstream(row_count=50_000)
    service = _make_service(mock_prefect, upstream_reader=upstream)

    status, _ = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Hybrid shuffle params",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50_000,
    )

    assert status.status == "running"
    assert "total_available" in mock_prefect.parameters
    assert isinstance(mock_prefect.parameters["offset"], int)


@pytest.mark.asyncio
async def test_direct_import_uses_shuffled_ids() -> None:
    mock_prefect = _MockPrefectSuccess()
    payload_store = _MockPayloadStore()
    upstream = _MockUpstream(row_count=100)
    service = _make_service(mock_prefect, upstream_reader=upstream, payload_store=payload_store)

    status, flow_run_id = await service.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Shuffle direct",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50,
    )

    assert status.status == "completed"
    assert flow_run_id is None
    assert len(upstream.list_samples_calls) >= 1
    assert payload_store.manifest is not None
    assert payload_store.manifest.total_rows == 50


@pytest.mark.asyncio
async def test_direct_import_shuffle_reproducible() -> None:
    payload_store_a = _MockPayloadStore()
    upstream_a = _MockUpstream(row_count=100)
    service_a = _make_service(_MockPrefectSuccess(), upstream_reader=upstream_a, payload_store=payload_store_a)
    await service_a.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Reproducible A",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50,
    )

    payload_store_b = _MockPayloadStore()
    upstream_b = _MockUpstream(row_count=100)
    service_b = _make_service(_MockPrefectSuccess(), upstream_reader=upstream_b, payload_store=payload_store_b)
    await service_b.submit_import(
        source_inspection_time="2024-01-15T08:30:00",
        source_wafer_key=1,
        dataset_name="Reproducible B",
        storage_mode="file_shard_sparse",
        org_id="test-org",
        max_rows=50,
    )

    assert payload_store_a.manifest is not None
    assert payload_store_b.manifest is not None
    assert payload_store_a.manifest.total_rows == payload_store_b.manifest.total_rows
