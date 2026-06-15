from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import polars as pl
import pytest

from app.modules.sc.adapter import ScDatasetStore
from app.modules.sc.domain.upstream_reader import ScUpstreamReader


@pytest.fixture
def mock_sc_db_path() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    yield db_path


@pytest.fixture
def mock_sc_db(mock_sc_db_path: str) -> Generator[str, None, None]:
    yield mock_sc_db_path


@pytest.fixture
def mock_wafer_db_reader() -> ScUpstreamReader:
    from dataclasses import dataclass

    mock_reader = AsyncMock()

    now = datetime.now(timezone.utc)
    _ts_s = int(now.timestamp())
    _ts_str = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    _insp_df = pl.DataFrame(
        [
            {
                "inspection_time": _ts_s,
                "wafer_key": 1,
                "lot_id": "LOT001",
                "wafer_id": "WAFER001",
                "center_x": 100_000_000,
                "center_y": 100_000_000,
                "origin_x": 0,
                "origin_y": 0,
                "die_size_x": 800_000,
                "die_size_y": 400_000,
                "layer_id": "LAYER01",
                "inspect_equip_id": "EQP01",
                "recipe_id": "RECIPE01",
                "defects": 3,
                "images": 3,
                "device": "DEV01",
            }
        ]
    )
    _empty_df = pl.DataFrame()

    _samples_df = pl.DataFrame(
        [
            {
                "sample_id": "S001",
                "defect_id": 1,
                "inspection_time": _ts_s,
                "wafer_key": 1,
                "wafer_x": 100_000_000,
                "wafer_y": 200_000_000,
                "die_x": 10,
                "die_y": 20,
                "index_x": 10,
                "index_y": 20,
                "rough_bin": 2,
                "class_number": 1,
                "defect_class": "SCRATCH",
                "lot_id": "LOT001",
                "test_id": 1,
                "adder": 0,
                "size_x": 100,
                "size_y": 100,
                "size_d": 100,
                "area": 10000,
                "final_bin": 0,
                "manual_bin": 0,
                "kill_ratio": 0.0,
                "cluster": 1,
                "images": 1,
                "reticle_x": 4_000_000,
                "reticle_y": 1_000_000,
                "review_images": [],
            },
            {
                "sample_id": "S002",
                "defect_id": 2,
                "inspection_time": _ts_s,
                "wafer_key": 1,
                "wafer_x": 200_000_000,
                "wafer_y": 300_000_000,
                "die_x": 20,
                "die_y": 30,
                "index_x": 20,
                "index_y": 30,
                "rough_bin": 1,
                "class_number": 2,
                "defect_class": "PARTICLE",
                "lot_id": "LOT001",
                "test_id": 2,
                "adder": 0,
                "images": 1,
                "reticle_x": 4_000_000,
                "reticle_y": 1_000_000,
                "review_images": [],
            },
            {
                "sample_id": "S003",
                "defect_id": 3,
                "inspection_time": _ts_s,
                "wafer_key": 1,
                "wafer_x": 300_000_000,
                "wafer_y": 400_000_000,
                "die_x": 30,
                "die_y": 40,
                "index_x": 30,
                "index_y": 40,
                "rough_bin": 3,
                "class_number": 1,
                "defect_class": "SCRATCH",
                "lot_id": "LOT001",
                "test_id": 3,
                "adder": 0,
                "images": 1,
                "reticle_x": 4_000_000,
                "reticle_y": 1_000_000,
                "review_images": [],
            },
        ]
    )

    @dataclass
    class _MockInspection:
        center_x: int = 100_000_000
        center_y: int = 100_000_000
        origin_x: int = 0
        origin_y: int = 0
        die_size_x: int = 800_000
        die_size_y: int = 400_000
        wafer_key: int = 1
        wafer_id: str = "WAFER001"
        lot_id: str = "LOT001"
        device: str = "DEV01"
        layer_id: str = "LAYER01"
        inspection_time: str = ""
        defects: int = 3
        images: int = 3

    async def _list_inspections(
        start_time, end_time, lot_id=None, wafer_id=None, layer_id=None, device=None
    ):
        if isinstance(start_time, datetime) and start_time.year < 2000:
            return _empty_df.lazy()
        return _insp_df.lazy()

    mock_reader.list_inspections = AsyncMock(side_effect=_list_inspections)
    mock_reader.list_samples = AsyncMock(return_value=_samples_df.lazy())
    mock_reader.get_inspection = AsyncMock(return_value=_MockInspection())
    _review_images_df = pl.DataFrame(
        [
            {
                "defect_id": 1,
                "image_filespec": "image_001.jpg",
                "image_id": 100,
                "image_type": "review",
            },
            {
                "defect_id": 1,
                "image_filespec": "image_002.jpg",
                "image_id": 101,
                "image_type": "review",
            },
        ]
    )

    mock_reader.list_review_images = AsyncMock(return_value=_review_images_df.lazy())

    return mock_reader


@pytest.fixture
def sc_store() -> ScDatasetStore:
    return ScDatasetStore()


@pytest.fixture
def mock_prefect_client():

    class MockPrefectClient:
        async def resolve_deployment_id(self, name: str) -> str:
            return "test-deployment-id"

        async def create_flow_run_from_deployment(
            self, deployment_id: str, parameters: dict
        ) -> dict:
            return {"id": "test-run-id-123"}

        async def get_flow_run(self, run_id: str) -> dict:
            return {"state_type": "COMPLETED", "state_message": ""}

    return MockPrefectClient()


@pytest.fixture
def mock_ls_client():

    class MockLSClient:
        async def create_project(self, name: str, label_config: str) -> dict:
            return {"id": 99}

    return MockLSClient()
