from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import func, select

from app.shared.db.registry import (
    ArtifactORM,
    Base,
    PredictionEventORM,
    PredictionJobORM,
    TrainingEventORM,
    TrainingJobORM,
)
from app.shared.db.session import create_engine, create_session_factory
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage
from seedmaker.dev_activity import (
    MODEL_IDS,
    PREDICTION_JOB_IDS,
    TRAINING_JOB_IDS,
    DevActivityContext,
    seed_dev_activity,
)


@pytest.mark.asyncio
async def test_seed_dev_activity_is_repeatable_without_external_runs() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    storage = InMemoryArtifactStorage()
    context = DevActivityContext(
        org_id="org-dev-seed",
        created_by="user-dev-seed",
        sc_dataset_id="dataset-dev-seed",
        sc_collection_id="collection-dev-seed",
        sc_collection_revision_id="revision-dev-seed",
        label_space=("normal", "scratch", "particle"),
        sc_sample_count=2500,
        sc_annotation_count=96,
    )
    now = datetime(2026, 8, 15, 8, tzinfo=UTC)

    first = await seed_dev_activity(session_factory, storage, context, now=now)
    second = await seed_dev_activity(session_factory, storage, context, now=now)

    assert first == second
    assert first.training_jobs == len(TRAINING_JOB_IDS)
    assert first.prediction_jobs == len(PREDICTION_JOB_IDS)
    assert first.models == len(MODEL_IDS)

    async with session_factory() as session:
        training_jobs = (
            await session.execute(
                select(TrainingJobORM).where(TrainingJobORM.id.in_(TRAINING_JOB_IDS))
            )
        ).scalars().all()
        prediction_jobs = (
            await session.execute(
                select(PredictionJobORM).where(
                    PredictionJobORM.id.in_(PREDICTION_JOB_IDS)
                )
            )
        ).scalars().all()
        model_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ArtifactORM)
                .where(ArtifactORM.id.in_(MODEL_IDS))
            )
            or 0
        )
        training_event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(TrainingEventORM)
                .where(TrainingEventORM.job_id.in_(TRAINING_JOB_IDS))
            )
            or 0
        )
        prediction_event_count = int(
            await session.scalar(
                select(func.count())
                .select_from(PredictionEventORM)
                .where(PredictionEventORM.job_id.in_(PREDICTION_JOB_IDS))
            )
            or 0
        )

    assert {job.status for job in training_jobs} == {
        "completed",
        "failed",
        "cancelled",
    }
    assert {job.status for job in prediction_jobs} == {
        "completed",
        "failed",
        "cancelled",
    }
    assert all(job.external_job_id is None for job in training_jobs)
    assert all(job.external_job_id is None for job in prediction_jobs)
    assert model_count == 2
    assert training_event_count == 7
    assert prediction_event_count == 5

    await engine.dispose()


def test_dev_showcase_items_share_collection_compatible_metadata_shape() -> None:
    from seedmaker.datasets.dev_showcase import _classification_item

    balanced = _classification_item(1, fully_labeled=True)
    review = _classification_item(1, fully_labeled=False, multi_image=True)

    assert set(balanced["metadata"]) == set(review["metadata"])
    assert balanced["label"] == "scratch"
    assert "label" not in review
    assert len(balanced["image_uris"]) == 1
    assert len(review["image_uris"]) == 3


class _SeedResponse:
    def __init__(self, body: Any) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._body


class _AutomationSeedClient:
    def __init__(self, *, existing: bool = False) -> None:
        self.existing = existing
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, **_: Any) -> _SeedResponse:
        if path == "/api/v1/source-connectors":
            return _SeedResponse(
                [
                    {
                        "id": "connector-dev",
                        "name": "Dev SC Upstream",
                        "provider_id": "sc",
                    }
                ]
                if self.existing
                else []
            )
        if path.endswith("/membership-rules"):
            return _SeedResponse(
                [
                    {
                        "name": "New SC inspections with defects",
                        "active_version": {"connector_id": "connector-dev"},
                    }
                ]
                if self.existing
                else []
            )
        raise AssertionError(f"Unexpected GET {path}")

    def post(self, path: str, *, json: dict[str, Any]) -> _SeedResponse:
        self.posts.append((path, json))
        if path == "/api/v1/source-connectors":
            return _SeedResponse(
                {
                    "id": "connector-dev",
                    "name": "Dev SC Upstream",
                    "provider_id": "sc",
                }
            )
        if path.endswith("/import-profiles"):
            return _SeedResponse({"id": "profile-dev"})
        if path.endswith("/membership-rules"):
            return _SeedResponse({"id": "rule-dev"})
        raise AssertionError(f"Unexpected POST {path}")


def test_dev_showcase_seeds_manual_only_membership_rule() -> None:
    from seedmaker import SeedRunner
    from seedmaker.datasets.dev_showcase import _ensure_source_membership_rule

    client = _AutomationSeedClient()
    _ensure_source_membership_rule(
        cast(SeedRunner, SimpleNamespace(client=client)),
        {"id": "collection-dev"},
    )

    assert [path for path, _ in client.posts] == [
        "/api/v1/source-connectors",
        "/api/v1/source-connectors/connector-dev/import-profiles",
        "/api/v1/dataset-collections/collection-dev/membership-rules",
    ]
    profile_payload = client.posts[1][1]
    assert "image_source_format" not in profile_payload["settings"]
    rule_payload = client.posts[-1][1]
    assert rule_payload["condition"] == {
        "kind": "group",
        "combinator": "all",
        "children": [
            {
                "kind": "predicate",
                "field": "defects",
                "operator": "gte",
                "value": 1,
            }
        ],
    }


def test_dev_showcase_reuses_existing_membership_rule() -> None:
    from seedmaker import SeedRunner
    from seedmaker.datasets.dev_showcase import _ensure_source_membership_rule

    client = _AutomationSeedClient(existing=True)
    _ensure_source_membership_rule(
        cast(SeedRunner, SimpleNamespace(client=client)),
        {"id": "collection-dev"},
    )

    assert client.posts == []
