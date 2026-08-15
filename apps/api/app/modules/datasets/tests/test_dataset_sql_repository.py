from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from app.shared.api.schemas import Dataset, DatasetStorageMode, TaskSpec
from app.shared.db.registry import Base, OrganizationORM
from app.shared.db.session import create_session_factory
from app.modules.datasets.adapter.repositories.dataset_sql_repository import DatasetSqlRepository


@pytest.mark.asyncio
async def test_update_dataset_meta_persists_json_update_across_sessions() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        session_factory = create_session_factory(engine)
        repo = DatasetSqlRepository(session_factory)
        org_id = str(uuid4())
        org_slug = f"repo-test-{uuid4().hex[:8]}"

        async with session_factory() as session:
            session.add(OrganizationORM(id=org_id, name=org_slug, slug=org_slug))
            await session.commit()

        dataset = Dataset(
            id=str(uuid4()),
            name="json-meta-persistence",
            dataset_type="image_sc",
            task_spec=TaskSpec(task_type="sc", label_space=[]),
            storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
            ls_project_id="SPARSE_NO_LS",
        )
        await repo.create_dataset(dataset, org_id=org_id)

        geometry = {
            "center_x": 100,
            "center_y": 200,
            "origin_x": 10,
            "origin_y": 20,
            "die_size_x": 5,
            "die_size_y": 6,
            "origin_index_x": 0,
            "origin_index_y": 1,
            "wafer_id": "WAFER-001",
            "lot_id": "LOT-001",
            "device": "DEVICE-X",
        }

        updated = await repo.update_dataset_meta(dataset.id, {"geometry": geometry})
        assert updated is not None
        assert updated.dataset_meta["geometry"] == geometry

        reloaded = await repo.get_dataset(dataset.id, org_id=org_id)
        assert reloaded is not None
        assert reloaded.dataset_meta["geometry"] == geometry
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sc_inspection_dataset_lookup_is_one_bulk_select() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        session_factory = create_session_factory(engine)
        repo = DatasetSqlRepository(session_factory)
        org_id = str(uuid4())
        org_slug = f"repo-test-{uuid4().hex[:8]}"
        source_time = "2026-08-15T10:30:00+00:00"

        async with session_factory() as session:
            session.add(OrganizationORM(id=org_id, name=org_slug, slug=org_slug))
            await session.commit()

        for index in range(8):
            dataset = Dataset(
                id=str(uuid4()),
                name=f"inspection-dataset-{index}",
                dataset_type="image_sc",
                task_spec=TaskSpec(task_type="sc", label_space=[]),
                storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
                ls_project_id="SPARSE_NO_LS",
            )
            await repo.create_dataset(dataset, org_id=org_id)
            await repo.update_dataset_meta(
                dataset.id,
                {
                    "source_inspection_time": source_time,
                    "source_wafer_key": index,
                },
                org_id=org_id,
            )

        select_count = 0

        def count_selects(_conn, _cursor, statement, *_args) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            datasets = await repo.list_datasets_for_sc_inspections(
                [source_time], org_id=org_id
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

        assert len(datasets) == 8
        assert select_count == 1
    finally:
        await engine.dispose()
