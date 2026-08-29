from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sc_upstream_simulator.artifacts import InspectionArtifactPublisher
from sc_upstream_simulator.models import Base, SimulatorClockORM
from sc_upstream_simulator.repository import SimulatorRepository, SimulatorStateError
from sc_upstream_simulator.scenarios import ShowcaseScenario, ShowcaseScenarioRunner


class RecordingObjectStore:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def ensure_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put(self, *, bucket: str, key: str, body: bytes, content_type: str) -> None:
        assert content_type in {"application/zip", "image/png"}
        self.objects[(bucket, key)] = body


@pytest.fixture
async def scenario_runner() -> tuple[
    ShowcaseScenarioRunner, SimulatorRepository, RecordingObjectStore
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    async with sessions() as session, session.begin():
        session.add(SimulatorClockORM(id=1, next_change_token=1))
    repository = SimulatorRepository(sessions)
    object_store = RecordingObjectStore()
    runner = ShowcaseScenarioRunner(
        repository=repository,
        artifacts=InspectionArtifactPublisher(
            object_store=object_store,
            patch_bucket="patches",
            review_bucket="reviews",
        ),
    )
    yield runner, repository, object_store
    await engine.dispose()


def _scenario(*, total_defects: int = 5) -> ShowcaseScenario:
    return ShowcaseScenario(
        inspection_time=datetime(2026, 8, 1, 4, tzinfo=timezone.utc),
        published_at=datetime(2026, 8, 1, 5, tzinfo=timezone.utc),
        total_defects=total_defects,
        imaged_defects=2,
        images_per_defect=2,
        gallery_defects=3,
        gallery_imaged_defects=1,
        defects_per_archive=2,
        append_batch_size=2,
    )


@pytest.mark.asyncio
async def test_showcase_publishes_records_and_objects_coherently(
    scenario_runner: tuple[
        ShowcaseScenarioRunner, SimulatorRepository, RecordingObjectStore
    ],
) -> None:
    runner, repository, object_store = scenario_runner

    result = await runner.publish(_scenario())

    assert [item.inspection.key.wafer_key for item in result.inspections] == [
        1,
        81,
        82,
        83,
    ]
    assert all(item.inspection.state == "published" for item in result.inspections)
    assert not any(item.reused for item in result.inspections)
    counts = await repository.child_counts(result.inspections[0].inspection.key)
    assert (counts.defects, counts.review_images, counts.patch_archives) == (5, 4, 3)
    assert object_store.buckets == {"patches", "reviews"}
    assert any(key.endswith(".zip") for _bucket, key in object_store.objects)
    assert any(key.endswith(".png") for _bucket, key in object_store.objects)

    replay = await runner.publish(_scenario())
    assert all(item.reused for item in replay.inspections)


@pytest.mark.asyncio
async def test_showcase_replay_rejects_different_shape(
    scenario_runner: tuple[
        ShowcaseScenarioRunner, SimulatorRepository, RecordingObjectStore
    ],
) -> None:
    runner, _repository, _object_store = scenario_runner
    await runner.publish(_scenario())

    with pytest.raises(SimulatorStateError, match="different defect"):
        await runner.publish(_scenario(total_defects=6))
