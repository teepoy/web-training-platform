"""Integration tests for GET /api/v1/sc/datasets/{id}/plot-points."""

from __future__ import annotations

from unittest.mock import AsyncMock

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.app.services.sc_plot_points_service import (
    ScPlotPointsNotFoundError,
    ScPlotPointsRejectedError,
    ScPlotPointsService,
)
from app.modules.sc.port.http.deps import get_sc_plot_points_service
from app.modules.sc.proto_adapter import make_wafer_map_response_pb
from proto_stubs.sc.v1.sample_pb2 import WaferMapResponse

PB_CONTENT_TYPE = "application/x-protobuf"
_DATASET_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_ENDPOINT = f"/api/v1/sc/datasets/{_DATASET_ID}/plot-points"
_DEFECT_IDS_ENDPOINT = f"/api/v1/sc/datasets/{_DATASET_ID}/defect-ids.bin"
_BOX_FILTER_ENDPOINT = f"/api/v1/sc/datasets/{_DATASET_ID}/box-filter"




def _make_service_mock(return_bytes: bytes) -> AsyncMock:
    svc = AsyncMock(spec=ScPlotPointsService)
    svc.ensure_plot_points_allowed = AsyncMock(return_value=None)
    svc.build_plot_points_response = AsyncMock(return_value=return_bytes)
    return svc


def _decode_int32le(body: bytes) -> list[int]:
    return [
        int.from_bytes(body[i : i + 4], "little", signed=True)
        for i in range(0, len(body), 4)
    ]


def test_plot_points_happy_path_100_samples() -> None:
    """100-sample sparse SC dataset returns 200 protobuf with 600-element arrays."""
    n = 100
    df = pl.DataFrame(
        {
            "defect_id": list(range(n)),
            "wafer_x": [i * 10 for i in range(n)],
            "wafer_y": [i * 5 for i in range(n)],
            "die_x": list(range(n)),
            "die_y": list(range(n)),
            "reticle_x": list(range(n)),
            "reticle_y": list(range(n)),
            "class_number": [0] * n,
            "rough_bin": [1] * n,
            "has_review": [0] * n,
        }
    )
    pb_bytes = make_wafer_map_response_pb(
        df,
        wafer_key=0,
        include_geometry=False,
        include_reticle_points=False,
    )
    mock_svc = _make_service_mock(pb_bytes)
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(PB_CONTENT_TYPE)
        msg = WaferMapResponse()
        msg.ParseFromString(resp.content)
        assert len(msg.wafer_points) == 600
        assert len(msg.die_points) == 600
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_stream_warms_then_keeps_protobuf_transport() -> None:
    mock_svc = _make_service_mock(b"\x08\x01")
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            stream_resp = client.get(f"{_ENDPOINT}/stream")
            pb_resp = client.get(_ENDPOINT)

        assert stream_resp.status_code == 200, stream_resp.text
        assert stream_resp.headers.get("content-type", "").startswith(
            "text/event-stream"
        )
        assert "event: progress" in stream_resp.text
        assert "event: done" in stream_resp.text

        assert pb_resp.status_code == 200, pb_resp.text
        assert pb_resp.headers.get("content-type", "").startswith(PB_CONTENT_TYPE)
        assert mock_svc.build_plot_points_response.await_count == 2
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_forwards_reticle_options() -> None:
    mock_svc = _make_service_mock(b"")
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(
                _ENDPOINT,
                params={
                    "reticleXDieCount": 4,
                    "reticleYDieCount": 6,
                    "reticleXDieShift": 1,
                    "reticleYDieShift": -2,
                },
            )
        assert resp.status_code == 200
        mock_svc.build_plot_points_response.assert_awaited_once_with(
                _DATASET_ID,
                "00000000-0000-0000-0000-000000000001",
                sampled=True,
                target_resolution=600,
                reticle_x_die_count=4,
                reticle_y_die_count=6,
                reticle_x_die_shift=1,
                reticle_y_die_shift=-2,
                legend_group_by=None,
                class_numbers=None,
                rough_bins=None,
                predictions=None,
                annotations=None,
                test_ids=None,
                adders=None,
                cluster_ids=None,
            )
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_empty_dataset() -> None:
    """Empty SC dataset (0 samples) → 200 OK with empty arrays."""
    df = pl.DataFrame(
        {
            "defect_id": [],
            "wafer_x": [],
            "wafer_y": [],
            "die_x": [],
            "die_y": [],
            "reticle_x": [],
            "reticle_y": [],
            "class_number": [],
            "rough_bin": [],
            "has_review": [],
        },
        schema={
            "defect_id": pl.Int32,
            "wafer_x": pl.Int32,
            "wafer_y": pl.Int32,
            "die_x": pl.Int32,
            "die_y": pl.Int32,
            "reticle_x": pl.Int32,
            "reticle_y": pl.Int32,
            "class_number": pl.Int32,
            "rough_bin": pl.Int32,
            "has_review": pl.Int32,
        },
    )
    pb_bytes = make_wafer_map_response_pb(
        df,
        wafer_key=0,
        include_geometry=False,
        include_reticle_points=False,
    )
    mock_svc = _make_service_mock(pb_bytes)
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(PB_CONTENT_TYPE)
        msg = WaferMapResponse()
        msg.ParseFromString(resp.content)
        assert len(msg.wafer_points) == 0
        assert len(msg.die_points) == 0
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_box_filter_forwards_region_and_reticle_options() -> None:
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.filter_dataset_box = AsyncMock(return_value=["10", "20"])
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.post(
                _BOX_FILTER_ENDPOINT,
                json={
                    "mode": "reticle",
                    "x": 1,
                    "y": 2,
                    "width": 30,
                    "height": 40,
                    "reticle_x_die_count": 4,
                    "reticle_y_die_count": 6,
                    "reticle_x_die_shift": 1,
                    "reticle_y_die_shift": -2,
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"defect_ids": ["10", "20"], "total": 2}
        mock_svc.filter_dataset_box.assert_awaited_once_with(
            _DATASET_ID,
            "00000000-0000-0000-0000-000000000001",
            mode="reticle",
            x=1.0,
            y=2.0,
            width=30.0,
            height=40.0,
            reticle_x_die_count=4,
            reticle_y_die_count=6,
            reticle_x_die_shift=1,
            reticle_y_die_shift=-2,
        )
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_dataset_defect_ids_binary_forwards_to_service() -> None:
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.build_defect_ids_response = AsyncMock(
        return_value=(1).to_bytes(4, "little", signed=True)
        + (7).to_bytes(4, "little", signed=True)
    )
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_DEFECT_IDS_ENDPOINT)

        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(
            "application/octet-stream"
        )
        assert _decode_int32le(resp.content) == [1, 7]
        mock_svc.build_defect_ids_response.assert_awaited_once_with(
            _DATASET_ID,
            "00000000-0000-0000-0000-000000000001",
        )
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_dataset_defect_ids_binary_empty_response() -> None:
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.build_defect_ids_response = AsyncMock(return_value=b"")
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_DEFECT_IDS_ENDPOINT)

        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(
            "application/octet-stream"
        )
        assert resp.content == b""
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_dataset_defect_ids_nonexistent_dataset_returns_404() -> None:
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.build_defect_ids_response = AsyncMock(
        side_effect=ScPlotPointsNotFoundError(_DATASET_ID)
    )
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_DEFECT_IDS_ENDPOINT)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_nonexistent_dataset_returns_404() -> None:
    """Non-existent dataset id → 404."""
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.ensure_plot_points_allowed = AsyncMock(
        side_effect=ScPlotPointsNotFoundError(_DATASET_ID)
    )
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_non_sc_dataset_returns_400() -> None:
    """Non-SC dataset (e.g., classification) → 400 with explanatory detail."""
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.ensure_plot_points_allowed = AsyncMock(
        side_effect=ScPlotPointsRejectedError("plot-points requires an image_sc dataset")
    )
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 400
        assert "image_sc" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


def test_plot_points_non_sparse_dataset_returns_400() -> None:
    """Non-sparse SC dataset (db_full) → 400 with explanatory detail."""
    mock_svc = AsyncMock(spec=ScPlotPointsService)
    mock_svc.ensure_plot_points_allowed = AsyncMock(
        side_effect=ScPlotPointsRejectedError(
            "plot-points requires a file_shard_sparse dataset"
        )
    )
    app.dependency_overrides[get_sc_plot_points_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 400
        assert "file_shard_sparse" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_sc_plot_points_service, None)


@pytest.mark.no_auth_override
def test_plot_points_no_auth_returns_401() -> None:
    """Missing auth token → 401."""
    with TestClient(app) as client:
        resp = client.get(_ENDPOINT)
    assert resp.status_code == 401


def test_plot_columns_omits_die_xy_to_avoid_pyarrow_fieldref_error() -> None:
    """Regression: sparse SC parquet has no die_x/die_y; requesting them
    triggers `pyarrow: No match for FieldRef.Name(die_x)` (production 500)."""
    assert "die_x" not in ScPlotPointsService._PLOT_COLUMNS
    assert "die_y" not in ScPlotPointsService._PLOT_COLUMNS
    assert "wafer_x" in ScPlotPointsService._PLOT_COLUMNS
    assert "wafer_y" in ScPlotPointsService._PLOT_COLUMNS


def test_plot_columns_uses_images_not_review_images() -> None:
    """Regression: sparse SC parquet column is `images` with role discriminator;
    `review_images` is a domain concept, not a parquet column. Requesting
    `review_images` triggers `pyarrow: No match for FieldRef.Name(review_images)`."""
    assert "review_images" not in ScPlotPointsService._PLOT_COLUMNS
    assert "images" in ScPlotPointsService._PLOT_COLUMNS


@pytest.mark.asyncio
async def test_build_defect_ids_response_sorts_numeric_ids() -> None:
    from unittest.mock import AsyncMock

    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.api.schemas import Dataset, DatasetStorageMode
    from app.shared.db.sql_repository import SqlRepository

    df = pl.DataFrame({"defect_id": [10, 2, 1]})

    mock_storage = AsyncMock()
    mock_storage.list_samples = AsyncMock(return_value=df.lazy())

    mock_storage_factory = AsyncMock(spec=DatasetStorageFactory)
    mock_storage_factory.open = AsyncMock(return_value=mock_storage)

    dataset = Dataset(
        id=_DATASET_ID,
        name="test-defect-ids",
        dataset_type="image_sc",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={"task_type": "sc", "label_space": []},
    )

    mock_repo = AsyncMock(spec=SqlRepository)
    mock_repo.get_dataset = AsyncMock(return_value=dataset)

    svc = ScPlotPointsService(
        repository=mock_repo,  # type: ignore
        storage_factory=mock_storage_factory,  # type: ignore
    )

    body = await svc.build_defect_ids_response(_DATASET_ID, "org")

    assert _decode_int32le(body) == [1, 2, 10]


@pytest.mark.asyncio
async def test_build_plot_points_response_with_geometry_in_dataset_meta() -> None:
    """Geometry stored in dataset_meta propagates to WaferMapResponse."""
    from unittest.mock import AsyncMock

    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.api.schemas import Dataset, DatasetStorageMode
    from app.shared.db.sql_repository import SqlRepository

    n = 10
    df = pl.DataFrame(
        {
            "defect_id": list(range(n)),
            "wafer_x": [i * 10 for i in range(n)],
            "wafer_y": [i * 5 for i in range(n)],
            "die_x": list(range(n)),
            "die_y": list(range(n)),
            "reticle_x": list(range(n)),
            "reticle_y": list(range(n)),
            "class_number": [0] * n,
            "rough_bin": [1] * n,
            "has_review": [0] * n,
            "images": [[] for _ in range(n)],
        }
    )

    mock_storage = AsyncMock()
    mock_storage.list_samples = AsyncMock(return_value=df.lazy())

    mock_storage_factory = AsyncMock(spec=DatasetStorageFactory)
    mock_storage_factory.open = AsyncMock(return_value=mock_storage)

    dataset = Dataset(
        id=_DATASET_ID,
        name="test-geometry",
        dataset_type="image_sc",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "task_type": "sc",
            "label_space": [],
            "geometry": {
                "center_x": 5000,
                "center_y": 3000,
                "origin_x": -1000,
                "origin_y": -2000,
                "die_size_x": 8000,
                "die_size_y": 6000,
                "origin_index_x": 0,
                "origin_index_y": 0,
                "wafer_radius_nm": 200_000_000,
            },
        },
    )

    mock_repo = AsyncMock(spec=SqlRepository)
    mock_repo.get_dataset = AsyncMock(return_value=dataset)

    svc = ScPlotPointsService(
        repository=mock_repo,  # type: ignore
        storage_factory=mock_storage_factory,  # type: ignore
    )

    pb_bytes = await svc.build_plot_points_response(
        dataset_id=_DATASET_ID,
        org_id="org",
    )
    msg = WaferMapResponse()
    msg.ParseFromString(pb_bytes)

    assert msg.geometry.center_x == 5000
    assert msg.geometry.center_y == 3000
    assert msg.geometry.origin_x == -1000
    assert msg.geometry.origin_y == -2000
    assert msg.geometry.die_size_x == 8000
    assert msg.geometry.die_size_y == 6000
    assert msg.geometry.wafer_radius_nm == 200_000_000


@pytest.mark.asyncio
async def test_build_plot_points_response_rejects_missing_geometry() -> None:
    """Missing geometry key in dataset_meta is rejected instead of defaulted."""
    from unittest.mock import AsyncMock

    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.api.schemas import Dataset, DatasetStorageMode
    from app.shared.db.sql_repository import SqlRepository

    n = 5
    df = pl.DataFrame(
        {
            "defect_id": list(range(n)),
            "wafer_x": [i * 10 for i in range(n)],
            "wafer_y": [i * 5 for i in range(n)],
            "die_x": list(range(n)),
            "die_y": list(range(n)),
            "reticle_x": list(range(n)),
            "reticle_y": list(range(n)),
            "class_number": [0] * n,
            "rough_bin": [1] * n,
            "has_review": [0] * n,
            "images": [[] for _ in range(n)],
        }
    )

    mock_storage = AsyncMock()
    mock_storage.list_samples = AsyncMock(return_value=df.lazy())

    mock_storage_factory = AsyncMock(spec=DatasetStorageFactory)
    mock_storage_factory.open = AsyncMock(return_value=mock_storage)

    # dataset_meta WITHOUT geometry key
    dataset = Dataset(
        id=_DATASET_ID,
        name="test-no-geometry",
        dataset_type="image_sc",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={"task_type": "sc", "label_space": []},
    )

    mock_repo = AsyncMock(spec=SqlRepository)
    mock_repo.get_dataset = AsyncMock(return_value=dataset)

    svc = ScPlotPointsService(
        repository=mock_repo,  # type: ignore
        storage_factory=mock_storage_factory,  # type: ignore
    )

    with pytest.raises(ScPlotPointsRejectedError, match="dataset_meta.geometry"):
        await svc.build_plot_points_response(
            dataset_id=_DATASET_ID,
            org_id="org",
        )


@pytest.mark.asyncio
async def test_build_plot_points_response_rejects_incomplete_geometry() -> None:
    """Incomplete geometry must not silently default center/die values."""
    from unittest.mock import AsyncMock

    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.api.schemas import Dataset, DatasetStorageMode
    from app.shared.db.sql_repository import SqlRepository

    df = pl.DataFrame(
        {
            "defect_id": [1],
            "wafer_x": [10],
            "wafer_y": [20],
            "die_x": [1],
            "die_y": [2],
            "class_number": [0],
            "rough_bin": [1],
            "has_review": [0],
            "images": [[]],
        }
    )

    mock_storage = AsyncMock()
    mock_storage.list_samples = AsyncMock(return_value=df.lazy())

    mock_storage_factory = AsyncMock(spec=DatasetStorageFactory)
    mock_storage_factory.open = AsyncMock(return_value=mock_storage)

    dataset = Dataset(
        id=_DATASET_ID,
        name="test-incomplete-geometry",
        dataset_type="image_sc",
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        dataset_meta={
            "task_type": "sc",
            "label_space": [],
            "geometry": {
                "origin_x": 0,
                "origin_y": 0,
                "die_size_x": 1,
                "die_size_y": 1,
                "origin_index_x": 0,
                "origin_index_y": 0,
            },
        },
    )

    mock_repo = AsyncMock(spec=SqlRepository)
    mock_repo.get_dataset = AsyncMock(return_value=dataset)

    svc = ScPlotPointsService(
        repository=mock_repo,  # type: ignore
        storage_factory=mock_storage_factory,  # type: ignore
    )

    with pytest.raises(ScPlotPointsRejectedError, match="missing keys"):
        await svc.build_plot_points_response(
            dataset_id=_DATASET_ID,
            org_id="org",
        )
