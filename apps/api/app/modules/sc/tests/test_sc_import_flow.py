from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from app.modules.sc.models import PatchSample
from app.modules.sc.domain.mapper import patch_sample_to_sample


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_patch_sample(sample_id: str) -> PatchSample:
    """Create a minimal PatchSample for testing."""
    return PatchSample(
        sample_id=sample_id,
        defect_id=sample_id,
        wafer_key=0,
    )


class _MockFlowContext:
    """Minimal mock AppContext for flow testing — provides sc / shared / datasets.

    Mirrors the shape returned by ``build_flow_app_context()`` so flows can
    resolve ``ctx.sc.repository``, ``ctx.shared.label_studio_client``,
    ``ctx.datasets.dataset_payload_store`` without local ``_build_sc_*`` helpers.
    """

    def __init__(self) -> None:
        self.sc: Any = MagicMock()
        self.shared: Any = MagicMock()
        self.datasets: Any = MagicMock()
        self._closed = False

    async def close(self) -> None:
        self._closed = True


def _install_mock_context(mock_ctx: _MockFlowContext) -> None:
    """Patch the flow context builder to return a mock AppContext."""
    import app.modules.sc.adapter.flows.sc_import as flow_mod

    if not hasattr(flow_mod, "_test_original_with_flow_app_context"):
        setattr(
            flow_mod,
            "_test_original_with_flow_app_context",
            flow_mod._with_flow_app_context,
        )
    flow_mod._with_flow_app_context = AsyncMock(return_value=(mock_ctx, False))


def _remove_mock_context() -> None:
    """Reset the flow module's context builder patch."""
    import app.modules.sc.adapter.flows.sc_import as flow_mod

    original = getattr(flow_mod, "_test_original_with_flow_app_context", None)
    if original is not None:
        flow_mod._with_flow_app_context = original
        delattr(flow_mod, "_test_original_with_flow_app_context")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScImportFlow:
    """Tests for the sc-import-upstream Prefect flow."""

    @pytest.mark.skip(
        reason="Requires Prefect server infra (temporary server alembic migration issue)"
    )
    def test_sc_import_creates_dataset_and_samples(self) -> None:
        """Flow creates LS project, dataset, streams samples, and returns result."""
        ctx = _MockFlowContext()

        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )

        from app.shared.api.schemas import Dataset, TaskSpec

        created_dataset = Dataset(
            id="ds-1",
            name="SC Test Dataset",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id="99",
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        ctx.sc.repository.create_samples = AsyncMock()

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_stream(self, source_inspection_time, source_wafer_key, offset=0):
                for i in range(1, 6):
                    yield _mock_patch_sample(str(i))

            with pytest.MonkeyPatch.context():
                result = asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Test Dataset",
                        storage_mode="db_full",
                        label_space=["pass", "fail"],
                    )
                )
        finally:
            _remove_mock_context()

        assert result["dataset_id"] == "ds-1"
        assert result["imported_count"] == 5

        ctx.shared.label_studio_client.create_project.assert_awaited_once()
        ls_call_args = ctx.shared.label_studio_client.create_project.call_args
        assert ls_call_args.args[0] == "SC Test Dataset"
        assert "Choices" in ls_call_args.args[1]

        ctx.sc.repository.create_dataset.assert_awaited_once()
        ds_call = ctx.sc.repository.create_dataset.call_args
        ds_arg = ds_call.args[0]
        assert ds_arg.dataset_type == "image_sc"
        assert ds_arg.task_spec.task_type == "sc"
        assert ds_arg.ls_project_id == "99"

        ctx.sc.repository.create_samples.assert_awaited_once()
        samples_call = ctx.sc.repository.create_samples.call_args
        samples_arg = samples_call.args[0]
        assert len(samples_arg) == 5
        for s in samples_arg:
            assert s.dataset_id == "ds-1"

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_sparse_path(self) -> None:
        """Sparse path skips LS project and SampleORM; writes Parquet shards."""
        ctx = _MockFlowContext()
        ctx.shared.config = MagicMock()
        ctx.shared.config.storage.minio.endpoint = "localhost:9000"
        ctx.shared.config.storage.minio.access_key = "minioadmin"
        ctx.shared.config.storage.minio.secret_key = "minioadmin"
        ctx.shared.config.storage.minio.secure = False
        from app.shared.api.schemas import Dataset, SPARSE_NO_LS, TaskSpec

        created_dataset = Dataset(
            id="ds-sparse-1",
            name="SC Sparse",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id=SPARSE_NO_LS,
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        from platform_runtime.sparse import ShardEntry

        ctx.datasets.dataset_payload_store.put_shard = AsyncMock(
            return_value=ShardEntry(
                shard_index=0,
                uri="s3://bucket/shard.parquet",
                row_count=5,
                format="parquet",
                checksum_sha256="abc",
                byte_size=100,
            )
        )
        ctx.datasets.dataset_payload_store.put_manifest = AsyncMock(
            return_value="s3://bucket/manifest.json"
        )
        _install_mock_context(ctx)
        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_stream(self, source_inspection_time, source_wafer_key, offset=0):
                for i in range(1, 6):
                    yield _mock_patch_sample(str(i))

            with pytest.MonkeyPatch.context():
                result = asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Sparse",
                        storage_mode="file_shard_sparse",
                        label_space=["pass", "fail"],
                    )
                )
        finally:
            _remove_mock_context()
        assert result["dataset_id"] == "ds-sparse-1"
        assert result["imported_count"] == 5
        ctx.shared.label_studio_client.create_project.assert_not_called()
        ctx.sc.repository.create_samples.assert_not_called()
        ctx.sc.repository.create_dataset.assert_awaited_once()
        ds_arg = ctx.sc.repository.create_dataset.call_args.args[0]
        assert ds_arg.ls_project_id == SPARSE_NO_LS
        assert ds_arg.storage_mode.value == "file_shard_sparse"
        ctx.datasets.dataset_payload_store.put_shard.assert_awaited()
        ctx.datasets.dataset_payload_store.put_manifest.assert_awaited_once()

    def test_sc_import_resolves_sc_deps_from_flow_context(self) -> None:
        """Flow context provides sc.repository, sc.upstream_reader, sc.image_fetcher.

        Verifies that the flow can resolve SC dependencies through the
        AppContext without local _build_sc_* helpers.
        """
        ctx = _MockFlowContext()

        assert ctx.sc is not None
        assert ctx.sc.repository is not None
        assert ctx.shared is not None
        assert ctx.shared.label_studio_client is not None
        assert ctx.datasets is not None
        assert ctx.datasets.dataset_payload_store is not None

    def test_sc_import_passes_offset_to_sparse_upstream(self) -> None:
        """Sparse flow keeps storage aggregate path and streams all data for in-memory shuffle."""

        class FakeUpstream:
            def __init__(self) -> None:
                self.list_samples_calls: list[tuple] = []

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
                rows = []
                for i in range(1, 101):
                    rows.append({
                        "sample_id": str(i),
                        "defect_id": str(i),
                        "inspection_time": "2024-01-15T08:30:00",
                        "wafer_key": 1,
                        "wafer_x": i,
                        "wafer_y": i,
                        "die_x": 0,
                        "die_y": 0,
                        "rough_bin": 1,
                        "class_number": 1,
                        "lot_id": "LOT-001",
                    })
                return pl.DataFrame(rows).lazy()

        class FakeStorage:
            def __init__(self) -> None:
                self.rows: list[Any] = []

            async def write_samples(
                self, rows, *, schema_columns=None, batch_size: int = 1000
            ) -> int:
                async for row in rows:
                    self.rows.append(row)
                return len(self.rows)

        ctx = _MockFlowContext()
        upstream = FakeUpstream()
        storage = FakeStorage()
        ctx.sc.upstream_reader = upstream
        ctx.datasets.dataset_storage_factory.open = AsyncMock(return_value=storage)

        _install_mock_context(ctx)
        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "app.modules.sc.adapter.flows.sc_import._build_image_structs",
                    AsyncMock(return_value=[]),
                )
                mp.setattr(
                    "app.modules.sc.adapter.flows.sc_import.get_run_logger",
                    lambda: logging.getLogger("test.sc_import"),
                )
                result = asyncio.run(
                    sc_import.fn(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Existing",
                        storage_mode="file_shard_sparse",
                        dataset_id="ds-existing",
                        org_id="test-org",
                        offset=30,
                    )
                )
        finally:
            _remove_mock_context()

        assert result["dataset_id"] == "ds-existing"
        assert result["imported_count"] == 70
        assert len(upstream.list_samples_calls) == 1
        assert len(storage.rows) == 70
        ctx.datasets.dataset_storage_factory.open.assert_awaited_once_with(
            "ds-existing", "test-org"
        )

    def test_sc_import_shuffle_reproducible(self) -> None:
        """Two calls to get_shuffled_ids with the same input produce the same order."""
        from app.modules.sc.app.services.shuffle import get_shuffled_ids

        all_ids = list(range(1, 101))
        first = get_shuffled_ids(all_ids)
        second = get_shuffled_ids(all_ids)
        assert first == second

    def test_sc_import_no_overlap_with_api(self) -> None:
        """API slice and worker slice of shuffled IDs have zero intersection."""
        from app.modules.sc.app.services.shuffle import get_shuffled_ids

        all_ids = list(range(1, 1001))
        shuffled = get_shuffled_ids(all_ids)
        api_ids = set(shuffled[:30])
        worker_ids = set(shuffled[30:])
        assert api_ids & worker_ids == set()
        assert len(api_ids) == 30
        assert len(worker_ids) == 970
        assert api_ids | worker_ids == set(all_ids)

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_uses_sc_dataset_type(self) -> None:
        """Flow passes dataset_type='image_sc' and task_type='sc' to repo."""
        ctx = _MockFlowContext()
        ctx.shared.config = MagicMock()
        ctx.shared.config.storage.minio.endpoint = "localhost:9000"
        ctx.shared.config.storage.minio.access_key = "minioadmin"
        ctx.shared.config.storage.minio.secret_key = "minioadmin"
        ctx.shared.config.storage.minio.secure = False
        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )
        from app.shared.api.schemas import Dataset, TaskSpec

        created_dataset = Dataset(
            id="ds-1",
            name="SC Test",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id="99",
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        ctx.sc.repository.create_samples = AsyncMock()
        _install_mock_context(ctx)
        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_stream(self, source_inspection_time, source_wafer_key, offset=0):
                return
                yield

            with pytest.MonkeyPatch.context():
                asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Test",
                    )
                )
        finally:
            _remove_mock_context()
        ctx.sc.repository.create_dataset.assert_awaited_once()
        ds_call = ctx.sc.repository.create_dataset.call_args
        ds_arg = ds_call.args[0]
        assert ds_arg.dataset_type == "image_sc"
        assert ds_arg.task_spec.task_type == "sc"

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_handles_upstream_error(self) -> None:
        """Flow returns error dict when upstream raises, without re-raising."""
        ctx = _MockFlowContext()
        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )

        from app.shared.api.schemas import Dataset, TaskSpec

        created_dataset = Dataset(
            id="ds-1",
            name="SC Test",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id="99",
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        ctx.sc.repository.create_samples = AsyncMock()

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_stream_error(self, source_inspection_time, source_wafer_key, offset=0):
                raise Exception("Connection refused")
                yield

            with pytest.MonkeyPatch.context():
                result = asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Test",
                        storage_mode="db_full",
                    )
                )
        finally:
            _remove_mock_context()

        assert "error" in result
        assert "Connection refused" in result["error"]
        assert result["imported_count"] == 0

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_handles_ls_error(self) -> None:
        """Flow returns error dict when LS project creation fails."""
        ctx = _MockFlowContext()
        ctx.shared.label_studio_client.create_project = AsyncMock(
            side_effect=Exception("LS unavailable")
        )
        ctx.sc.repository.create_dataset = AsyncMock()
        ctx.sc.repository.create_samples = AsyncMock()

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            result = asyncio.run(
                sc_import(
                    source_inspection_time="2024-01-15T08:30:00",
                    source_wafer_key=1,
                    dataset_name="SC Test",
                    storage_mode="db_full",
                )
            )
        finally:
            _remove_mock_context()

        assert "error" in result
        assert "LS unavailable" in result["error"]
        assert result["imported_count"] == 0

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_handles_repo_error(self) -> None:
        """Flow returns error dict when dataset creation fails."""
        ctx = _MockFlowContext()
        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            side_effect=Exception("DB connection lost")
        )
        ctx.sc.repository.create_samples = AsyncMock()

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            result = asyncio.run(
                sc_import(
                    source_inspection_time="2024-01-15T08:30:00",
                    source_wafer_key=1,
                    dataset_name="SC Test",
                )
            )
        finally:
            _remove_mock_context()

        assert "error" in result
        assert "DB connection lost" in result["error"]
        assert result["imported_count"] == 0

    @pytest.mark.skip(reason="Requires Prefect server infra")
    def test_sc_import_empty_upstream(self) -> None:
        """Flow returns imported_count=0 when upstream yields no samples."""
        ctx = _MockFlowContext()
        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )

        from app.shared.api.schemas import Dataset, TaskSpec

        created_dataset = Dataset(
            id="ds-1",
            name="SC Empty",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id="99",
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        ctx.sc.repository.create_samples = AsyncMock()

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_empty_stream(self, source_inspection_time, source_wafer_key, offset=0):
                return
                yield

            with pytest.MonkeyPatch.context():
                result = asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Empty",
                        storage_mode="db_full",
                    )
                )
        finally:
            _remove_mock_context()

        assert result["dataset_id"] == "ds-1"
        assert result["imported_count"] == 0
        ctx.sc.repository.create_samples.assert_not_called()

    @pytest.mark.skip(
        reason="Requires Prefect server infra (temporary server alembic migration issue)"
    )
    def test_sc_import_persists_geometry(self) -> None:
        """Flow persists wafer geometry into dataset_meta after dataset creation."""
        from datetime import datetime, timezone

        from app.modules.sc.domain.models import ScInspectionRecord

        ctx = _MockFlowContext()
        ctx.shared.label_studio_client.create_project = AsyncMock(
            return_value={"id": 99}
        )

        from app.shared.api.schemas import Dataset, TaskSpec

        created_dataset = Dataset(
            id="ds-geo-1",
            name="SC Geo Test",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc"),
            ls_project_id="99",
        )
        ctx.sc.repository.create_dataset = AsyncMock(
            return_value=created_dataset
        )
        ctx.sc.repository.update_dataset_meta = AsyncMock()

        insp_record = ScInspectionRecord(
            inspection_time=datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc),
            wafer_key=1,
            center_x=100,
            center_y=200,
            origin_x=10,
            origin_y=20,
            die_size_x=5,
            die_size_y=5,
            origin_index_x=0,
            origin_index_y=0,
            wafer_id="WAFER-001",
            lot_id="LOT-001",
            device="DEVICE-X",
        )
        ctx.sc.upstream_reader.get_inspection = AsyncMock(
            return_value=insp_record
        )

        _install_mock_context(ctx)

        try:
            from app.modules.sc.adapter.flows.sc_import import sc_import

            async def mock_stream(self, source_inspection_time, source_wafer_key, offset=0):
                for i in range(1, 4):
                    yield _mock_patch_sample(str(i))

            with pytest.MonkeyPatch.context():
                result = asyncio.run(
                    sc_import(
                        source_inspection_time="2024-01-15T08:30:00",
                        source_wafer_key=1,
                        dataset_name="SC Geo Test",
                        storage_mode="file_shard_sparse",
                    )
                )
        finally:
            _remove_mock_context()

        assert result["dataset_id"] == "ds-geo-1"
        ctx.sc.repository.update_dataset_meta.assert_awaited_once()
        call_args = ctx.sc.repository.update_dataset_meta.call_args
        assert call_args.args[0] == "ds-geo-1"
        meta_update = call_args.args[1]
        assert "geometry" in meta_update
        geometry = meta_update["geometry"]
        assert geometry["center_x"] == 100
        assert geometry["center_y"] == 200
        assert geometry["origin_x"] == 10
        assert geometry["origin_y"] == 20
        assert geometry["die_size_x"] == 5
        assert geometry["die_size_y"] == 5
        assert geometry["origin_index_x"] == 0
        assert geometry["origin_index_y"] == 0
        assert geometry["wafer_id"] == "WAFER-001"
        assert geometry["lot_id"] == "LOT-001"
        assert geometry["device"] == "DEVICE-X"


# ---------------------------------------------------------------------------
# T20: Platform/domain sample ID decoupling — model-level verification
# ---------------------------------------------------------------------------


class TestScSampleDecoupling:
    """Verify platform/domain sample ID boundary (T10 → T20)."""

    def _make_decorated_sample(
        self,
        sample_id: str = "UPSTREAM-001",
        defect_id: str = "DEF-042",
        wafer_key: int = 7,
        lot_id: str = "LOT-A1",
    ) -> PatchSample:
        """Build a PatchSample with known upstream identity fields."""
        return PatchSample(
            sample_id=sample_id,
            defect_id=defect_id,
            wafer_key=wafer_key,
            lot_id=lot_id,
        )

    # ------------------------------------------------------------------
    # mapper UUID generation
    # ------------------------------------------------------------------

    def test_full_db_import_to_sample_generates_uuid_not_upstream_id(self) -> None:
        """Platform Sample.id is UUID4, not the upstream sample_id."""
        from uuid import UUID

        decorated = self._make_decorated_sample(sample_id="UPSTREAM-001")
        sample = patch_sample_to_sample(decorated, dataset_id="ds-test")

        # Platform id is a valid UUID
        uuid_obj = UUID(sample.id)
        assert uuid_obj.version == 4, f"Expected UUID4, got version={uuid_obj.version}"

        # Platform id is NOT the upstream sample_id
        assert sample.id != "UPSTREAM-001", (
            f"Platform id leaked upstream sample_id: {sample.id}"
        )

    def test_full_db_import_repeat_yields_distinct_platform_ids(self) -> None:
        """Importing the same upstream data twice yields distinct UUIDs."""
        decorated_a = self._make_decorated_sample(sample_id="UPSTREAM-001")
        decorated_b = self._make_decorated_sample(sample_id="UPSTREAM-001")

        sample_a = patch_sample_to_sample(decorated_a, dataset_id="ds-test")
        sample_b = patch_sample_to_sample(decorated_b, dataset_id="ds-test")

        # Same upstream identity, different platform UUIDs
        assert sample_a.id != sample_b.id, (
            f"Repeat import reused platform id: {sample_a.id}"
        )

        # Both are valid UUIDs
        from uuid import UUID

        UUID(sample_a.id)
        UUID(sample_b.id)

    def test_full_db_import_repeat_same_dataset_no_pk_collision(self) -> None:
        """Two imports into the same dataset produce distinct UUIDs."""
        decorated_a = self._make_decorated_sample(sample_id="UPSTREAM-001")
        decorated_b = self._make_decorated_sample(sample_id="UPSTREAM-001")

        dataset_id = "ds-same"
        sample_a = patch_sample_to_sample(decorated_a, dataset_id=dataset_id)
        sample_b = patch_sample_to_sample(decorated_b, dataset_id=dataset_id)

        assert sample_a.dataset_id == sample_b.dataset_id == dataset_id
        assert sample_a.id != sample_b.id, (
            f"Same-dataset repeat import produced colliding ids: {sample_a.id}"
        )

    # ------------------------------------------------------------------
    # mapper upstream identity preservation
    # ------------------------------------------------------------------

    def test_full_db_import_metadata_preserves_upstream_sample_id(self) -> None:
        """After import, metadata contains the upstream sample_id."""
        decorated = self._make_decorated_sample(sample_id="UPSTREAM-001")
        sample = patch_sample_to_sample(decorated, dataset_id="ds-test")

        assert sample.metadata["sample_id"] == "UPSTREAM-001"

    def test_full_db_import_metadata_preserves_defect_id(self) -> None:
        """After import, metadata contains the upstream defect_id."""
        decorated = self._make_decorated_sample(defect_id="DEF-042")
        sample = patch_sample_to_sample(decorated, dataset_id="ds-test")

        assert sample.metadata["defect_id"] == "DEF-042"

    def test_full_db_import_metadata_preserves_lot_id(self) -> None:
        """After import, metadata contains the upstream lot_id."""
        decorated = self._make_decorated_sample(lot_id="LOT-A1")
        sample = patch_sample_to_sample(decorated, dataset_id="ds-test")

        assert sample.metadata["lot_id"] == "LOT-A1"

    def test_full_db_import_metadata_preserves_wafer_key(self) -> None:
        """After import, metadata contains the upstream wafer_key."""
        decorated = self._make_decorated_sample(wafer_key=7)
        sample = patch_sample_to_sample(decorated, dataset_id="ds-test")

        assert sample.metadata["wafer_key"] == 7

    def test_full_db_import_metadata_preserves_all_upstream_identity(self) -> None:
        """Metadata preserves sample_id, defect_id, lot_id, wafer_key,
        wafer_x, wafer_y, rough_bin simultaneously."""
        from datetime import datetime, timezone

        decorated = PatchSample(
            sample_id="UPSTREAM-ALL",
            defect_id="DEF-ALL",
            lot_id="LOT-ALL",
            wafer_key=99,
            wafer_x=10,
            wafer_y=20,
            rough_bin=3,
            inspection_time=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        sample = patch_sample_to_sample(decorated, dataset_id="ds-meta")

        meta = sample.metadata
        assert meta["sample_id"] == "UPSTREAM-ALL"
        assert meta["defect_id"] == "DEF-ALL"
        assert meta["lot_id"] == "LOT-ALL"
        assert meta["wafer_key"] == 99
        assert meta["wafer_x"] == 10
        assert meta["wafer_y"] == 20
        assert meta["rough_bin"] == 3

        # Platform id remains a UUID, not the upstream sample_id
        assert sample.id != "UPSTREAM-ALL"
        from uuid import UUID

        UUID(sample.id)

    # ------------------------------------------------------------------
    # shard_images → image_uris propagation
    # ------------------------------------------------------------------

    def test_full_db_import_to_sample_populates_image_uris(self) -> None:
        """Import populates image_uris from shard_images."""
        from app.modules.sc.domain.models import ShardImageRef

        decorated = PatchSample(
            sample_id="IMG-001",
            shard_images=[
                ShardImageRef(image_id="img-a", image_type="patch"),
                ShardImageRef(image_id="img-b", image_type="reference"),
            ],
        )
        sample = patch_sample_to_sample(decorated, dataset_id="ds-imgs")

        assert sample.image_uris == ["img-a", "img-b"]
