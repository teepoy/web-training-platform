from __future__ import annotations

from collections.abc import AsyncIterator
import os

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sc_upstream_simulator.api import create_control_app
from sc_upstream_simulator.models import (
    Base,
    DefectORM,
    InspectionORM,
    PatchArchiveORM,
    ReviewImageORM,
    SimulatorClockORM,
)
from sc_upstream_simulator.repository import SimulatorRepository


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    database_url = os.environ.get(
        "SC_SIMULATOR_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"
    )
    engine = create_async_engine(database_url)
    if database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with sessions() as session, session.begin():
        for model in (
            PatchArchiveORM,
            ReviewImageORM,
            DefectORM,
            InspectionORM,
            SimulatorClockORM,
        ):
            await session.execute(delete(model))
        session.add(SimulatorClockORM(id=1, next_change_token=1))
    app = create_control_app(
        repository=SimulatorRepository(sessions), api_token="test-token"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://simulator.test",
        headers={"Authorization": "Bearer test-token"},
    ) as test_client:
        yield test_client
    await engine.dispose()


def _create_body() -> dict[str, object]:
    return {
        "wafer_key": 7,
        "inspection_time": "2026-08-29T01:02:00Z",
        "lot_id": "LOT-1",
        "wafer_id": "WAFER-1",
        "layer_id": "LAYER-1",
        "device": "DEVICE-1",
        "inspect_equip_id": "EQP-1",
        "recipe_key": 11,
        "recipe_id": "RECIPE-1",
        "origin_index_x": 0,
        "origin_index_y": 0,
        "center_x": 1000,
        "center_y": 1000,
        "origin_x": 0,
        "origin_y": 0,
        "die_size_x": 20,
        "die_size_y": 30,
        "defects": [],
        "review_images": [],
        "patch_archives": [],
    }


@pytest.mark.asyncio
async def test_control_api_requires_bearer_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/inspections", headers={"Authorization": ""})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_append_publish_update_and_inspect(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post("/api/v1/inspections", json=_create_body())
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "draft"

    appended = await client.post(
        "/api/v1/inspections/records",
        json={
            "wafer_key": 7,
            "inspection_time": "2026-08-29T01:02:00Z",
            "defects": [
                {
                    "defect_id": 10,
                    "test_id": 1,
                    "class_number": 2,
                    "rough_bin": 3,
                    "wafer_x": 100,
                    "wafer_y": 200,
                    "index_x": 4,
                    "index_y": 5,
                    "adder": 0,
                    "cluster": 0,
                    "images": 0,
                    "size_x": 8,
                    "size_y": 9,
                    "size_d": 10,
                    "area": 72,
                    "final_bin": 2,
                    "manual_bin": 0,
                    "kill_ratio": 0.5,
                }
            ],
            "review_images": [],
            "patch_archives": [],
        },
    )
    assert appended.status_code == 204

    published = await client.post(
        "/api/v1/inspections/publish",
        json={
            "wafer_key": 7,
            "inspection_time": "2026-08-29T01:02:00Z",
            "published_at": "2026-08-29T01:05:00Z",
        },
    )
    assert published.status_code == 200
    assert published.json()["change_token"] == 1

    changed = await client.patch(
        "/api/v1/inspections",
        json={
            "wafer_key": 7,
            "inspection_time": "2026-08-29T01:02:00Z",
            "changed_at": "2026-08-29T01:06:00Z",
            "device": "DEVICE-2",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["change_token"] == 2

    inspected = await client.post(
        "/api/v1/inspections/inspect",
        json={
            "wafer_key": 7,
            "inspection_time": "2026-08-29T01:02:00Z",
        },
    )
    assert inspected.status_code == 200
    assert inspected.json()["device"] == "DEVICE-2"
    assert inspected.json()["last_updated_at"] == "2026-08-29T01:06:00Z"

    published_rows = await client.get("/api/v1/inspections?state=published")
    assert published_rows.status_code == 200
    assert len(published_rows.json()) == 1

    rejected_append = await client.post(
        "/api/v1/inspections/records",
        json={
            "wafer_key": 7,
            "inspection_time": "2026-08-29T01:02:00Z",
            "defects": [],
            "review_images": [],
            "patch_archives": [
                {
                    "archive_id": 1,
                    "s3_bucket": "sc-patch-images",
                    "s3_key": "7/inspection.zip",
                }
            ],
        },
    )
    assert rejected_append.status_code == 409
