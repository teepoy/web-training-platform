from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sc_upstream_simulator.domain import (
    DefectDraft,
    InspectionDraft,
    InspectionKey,
    PatchArchiveDraft,
    ReviewImageDraft,
)
from sc_upstream_simulator.models import (
    Base,
    DefectORM,
    InspectionORM,
    PatchArchiveORM,
    ReviewImageORM,
    SimulatorClockORM,
)
from sc_upstream_simulator.repository import (
    SimulatorConflictError,
    SimulatorRepository,
    SimulatorStateError,
)
from sc_upstream_simulator.upstream_adapter import SimulatorUpstreamAdapter


@pytest.fixture
async def repository(
    tmp_path: Path,
) -> AsyncIterator[tuple[SimulatorRepository, async_sessionmaker[AsyncSession], str]]:
    database_url = os.environ.get(
        "SC_SIMULATOR_TEST_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'simulator.db'}",
    )
    engine = create_async_engine(database_url)
    if database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
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

    yield SimulatorRepository(sessions), sessions, database_url
    await engine.dispose()


def _draft(*, duplicate_defects: bool = False) -> InspectionDraft:
    defect = DefectDraft(
        defect_id=10,
        test_id=1,
        class_number=2,
        rough_bin=3,
        wafer_x=100,
        wafer_y=200,
        index_x=4,
        index_y=5,
        adder=0,
        cluster=0,
        images=1,
        size_x=8,
        size_y=9,
        size_d=10,
        area=72,
        final_bin=2,
        manual_bin=0,
        kill_ratio=0.5,
    )
    return InspectionDraft(
        key=InspectionKey(
            wafer_key=7,
            inspection_time=datetime(2026, 8, 29, 1, 2, tzinfo=timezone.utc),
        ),
        lot_id="LOT-1",
        wafer_id="WAFER-1",
        layer_id="LAYER-1",
        device="DEVICE-1",
        inspect_equip_id="EQP-1",
        recipe_key=11,
        recipe_id="RECIPE-1",
        origin_index_x=0,
        origin_index_y=0,
        center_x=1000,
        center_y=1000,
        origin_x=0,
        origin_y=0,
        die_size_x=20,
        die_size_y=30,
        defects=(defect, defect) if duplicate_defects else (defect,),
        review_images=(
            ReviewImageDraft(
                defect_id=10,
                image_id=1,
                image_type="reference",
                image_filespec="s3://sc-review-images/7/10/1.png",
            ),
        ),
        patch_archives=(
            PatchArchiveDraft(
                archive_id=1,
                s3_bucket="sc-patch-images",
                s3_key="7/inspection.zip",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_create_then_publish_allocates_one_visible_change_token(
    repository: tuple[SimulatorRepository, async_sessionmaker[AsyncSession], str],
) -> None:
    repo, sessions, _ = repository
    draft = _draft()

    await repo.create_draft(draft)
    published_at = datetime(2026, 8, 29, 1, 5, tzinfo=timezone.utc)
    publication = await repo.publish(draft.key, published_at=published_at)

    assert publication.change_token == 1
    assert publication.last_updated_at == published_at
    async with sessions() as session:
        inspection = await session.get(
            InspectionORM, (draft.key.wafer_key, draft.key.inspection_time)
        )
        assert inspection is not None
        assert inspection.state == "published"
        assert inspection.change_token == 1
        assert await session.scalar(select(func.count()).select_from(DefectORM)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ReviewImageORM)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(PatchArchiveORM)) == 1
        )


@pytest.mark.asyncio
async def test_failed_child_insert_rolls_back_whole_draft(
    repository: tuple[SimulatorRepository, async_sessionmaker[AsyncSession], str],
) -> None:
    repo, sessions, _ = repository
    draft = _draft(duplicate_defects=True)

    with pytest.raises(SimulatorConflictError):
        await repo.create_draft(draft)

    async with sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(InspectionORM)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(DefectORM)) == 0


@pytest.mark.asyncio
async def test_published_inspection_cannot_be_published_again(
    repository: tuple[SimulatorRepository, async_sessionmaker[AsyncSession], str],
) -> None:
    repo, _, _ = repository
    draft = _draft()
    published_at = datetime(2026, 8, 29, 1, 5, tzinfo=timezone.utc)
    await repo.create_draft(draft)
    await repo.publish(draft.key, published_at=published_at)

    with pytest.raises(SimulatorStateError):
        await repo.publish(draft.key, published_at=published_at)


def test_inspection_identity_requires_timezone() -> None:
    with pytest.raises(ValueError, match="inspection_time must include a timezone"):
        InspectionKey(wafer_key=7, inspection_time=datetime(2026, 8, 29, 1, 2))


@pytest.mark.asyncio
async def test_published_state_is_exposed_live_through_transport_adapter(
    repository: tuple[
        SimulatorRepository,
        async_sessionmaker[AsyncSession],
        str,
    ],
) -> None:
    repo, sessions, database_url = repository
    draft = _draft()
    adapter = SimulatorUpstreamAdapter(sessions, database_url=database_url)
    try:
        await repo.create_draft(draft)
        assert (
            await adapter.get_inspection(draft.key.inspection_time, draft.key.wafer_key)
            is None
        )

        published_at = datetime(2026, 8, 29, 1, 5, tzinfo=timezone.utc)
        await repo.publish(draft.key, published_at=published_at)

        inspection = await adapter.get_inspection(
            draft.key.inspection_time, draft.key.wafer_key
        )
        assert inspection is not None
        assert inspection["device"] == "DEVICE-1"
        assert inspection["change_token"] == 1
        assert inspection["defects"] == 1
        assert inspection["images"] == 1

        listed = await adapter.list_inspections(
            datetime(2026, 8, 29, tzinfo=timezone.utc),
            datetime(2026, 8, 30, tzinfo=timezone.utc),
            lot_id="LOT-*",
        )
        assert listed.collect().height == 1
        assert (
            await adapter.get_sample_count(
                draft.key.inspection_time, draft.key.wafer_key
            )
            == 1
        )
        samples = (
            await adapter.list_samples(draft.key.inspection_time, draft.key.wafer_key)
        ).collect()
        assert samples["defect_id"].to_list() == [10]
        assert samples["die_x"].to_list() == [0]
        assert "die_y" in samples.columns
        stream = adapter.open_list_samples_stream(
            draft.key.inspection_time,
            draft.key.wafer_key,
            batch_size=1,
        )
        assert "defect_id" in stream.schema.names
        assert sum(batch.height for batch in stream.batches) == 1
        assert (
            len(
                await adapter.list_review_images(
                    draft.key.inspection_time, draft.key.wafer_key
                )
            )
            == 1
        )
        assert await adapter.get_inspection_patch_zips(
            draft.key.inspection_time,
            draft.lot_id,
            draft.wafer_id,
            draft.device,
            draft.layer_id,
        ) == [{"s3_bucket": "sc-patch-images", "s3_key": "7/inspection.zip"}]

        await repo.update_published(
            draft.key,
            changed_at=datetime(2026, 8, 29, 1, 6, tzinfo=timezone.utc),
            changes={"device": "DEVICE-2"},
        )
        changed = await adapter.get_inspection(
            draft.key.inspection_time, draft.key.wafer_key
        )
        assert changed is not None
        assert changed["device"] == "DEVICE-2"
        assert changed["change_token"] == 2
    finally:
        adapter.close()
