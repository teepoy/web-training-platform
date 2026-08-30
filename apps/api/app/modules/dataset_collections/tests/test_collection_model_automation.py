from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.registrations  # noqa: F401
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.dataset_collections.adapter.repositories.sql_repository import (
    DatasetCollectionSqlRepository,
)
from app.modules.dataset_collections.app.services.collection_model_automation_service import (
    CollectionModelAutomationService,
    CollectionRevisionPublishingService,
)
from app.modules.dataset_collections.domain.models import (
    CollectionPredictionBatch,
    CollectionPredictionBatchItem,
    CollectionPredictionObservation,
    DatasetCollection,
    DatasetCollectionRevision,
    PredictionCoverageStatus,
)
from app.modules.prediction.domain.submission import PredictionSubmissionOrigin
from app.shared.api.schemas import JobStatus, Model
from app.shared.db.models.dataset_collections import (
    CollectionPredictionBatchORM,
    DatasetCollectionORM,
)
from app.shared.db.registry import Base, OrganizationORM
from app.shared.db.session import create_session_factory


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _collection(*, model_id: str | None = "model-1") -> DatasetCollection:
    return DatasetCollection(
        id="collection-1",
        org_id="org-1",
        name="Collection",
        description="",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        duplicate_policy="keep_all",
        missing_data_policy="fail",
        definition_version=2,
        created_by="user-1",
        created_at=_now(),
        updated_at=_now(),
        default_model_id=model_id,
        model_binding_version=1,
    )


def _revision(
    number: int,
    *members: tuple[str, str, str],
) -> DatasetCollectionRevision:
    return DatasetCollectionRevision(
        id=f"revision-{number}",
        collection_id="collection-1",
        revision_number=number,
        definition_version=number,
        definition_hash=f"hash-{number}",
        target_view_id="patch_image_v1",
        target_view_contract="sc.patch-image",
        target_schema_version="1",
        status="ready",
        members=tuple(
            {
                "member_id": member_id,
                "source_dataset_id": dataset_id,
            }
            for member_id, dataset_id, _revision_id in members
        ),
        manifest_uri=f"memory://revision-{number}.json",
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=_now(),
        error_code=None,
        error_detail=None,
    )


def _dataset_revisions(**revision_ids: str) -> AsyncMock:
    reader = AsyncMock()
    reader.list_current.side_effect = lambda dataset_ids, _org_id: {
        dataset_id: SimpleNamespace(id=revision_ids[dataset_id])
        for dataset_id in dataset_ids
    }
    return reader


def _model() -> Model:
    return Model(
        id="model-1",
        uri="memory://model.pt",
        kind="model",
        metadata={
            "model_contract": "sc.yolo.model.v1",
            "model_schema_version": "1",
        },
        job_id="training-1",
        trainer_id="yolo-sc-v1",
    )


@pytest.mark.asyncio
async def test_default_model_change_never_dispatches_prediction() -> None:
    repository = AsyncMock()
    repository.get_collection.return_value = _collection(model_id=None)
    repository.set_default_model.return_value = _collection()
    model_catalog = AsyncMock()
    model_catalog.get_org_model.return_value = _model()
    prediction_execution = AsyncMock()
    service = CollectionModelAutomationService(
        repository=repository,
        model_catalog=model_catalog,
        prediction_execution=prediction_execution,
        dataset_revisions=AsyncMock(),
    )

    updated = await service.set_default_model(
        "collection-1",
        "org-1",
        actor_id="user-1",
        expected_binding_version=0,
        model_id="model-1",
    )

    assert updated.default_model_id == "model-1"
    model_catalog.get_org_model.assert_awaited_once_with("model-1", "org-1")
    repository.set_default_model.assert_awaited_once_with(
        "collection-1",
        "org-1",
        expected_binding_version=0,
        model_id="model-1",
    )
    prediction_execution.submit_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_incremental_prediction_only_dispatches_new_uncovered_member() -> None:
    previous = _revision(1, ("member-old", "dataset-old", "revision-old"))
    current = _revision(
        2,
        ("member-old", "dataset-old", "revision-old"),
        ("member-covered", "dataset-covered", "revision-covered"),
        ("member-new", "dataset-new", "revision-new"),
    )
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.get_revision.return_value = current
    repository.get_current_revision.return_value = current
    repository.list_revisions.return_value = [current, previous]
    repository.list_prediction_batches.return_value = []
    repository.list_prediction_observations.return_value = [
        CollectionPredictionObservation(
            member_id="member-covered",
            dataset_id="dataset-covered",
            prediction_job_id="prediction-existing",
            dataset_revision_id="revision-covered",
            model_id="model-1",
            status=JobStatus.COMPLETED.value,
            created_at=_now(),
        )
    ]
    stored_items: dict[str, CollectionPredictionBatchItem] = {}

    async def update_item(item_id: str, **updates: object) -> CollectionPredictionBatchItem:
        item = next(item for item in created_items if item.id == item_id)
        updated = CollectionPredictionBatchItem(
            id=item.id,
            batch_id=item.batch_id,
            member_id=item.member_id,
            dataset_id=item.dataset_id,
            dataset_revision_id=item.dataset_revision_id,
            prediction_job_id=str(updates["prediction_job_id"]),
            status=str(updates["status"]),
            attempt_count=1,
            error_detail=None,
            created_at=item.created_at,
            updated_at=_now(),
        )
        stored_items[item_id] = updated
        return updated

    created_items: list[CollectionPredictionBatchItem] = []
    created_batch = None

    async def create_batch(batch, items, _org_id):
        nonlocal created_batch
        if created_batch is not None:
            return created_batch, list(created_items), False
        created_batch = batch
        assert items == ()
        return batch, [], True

    async def add_batch_items(batch_id, items):
        assert created_batch is not None
        assert batch_id == created_batch.id
        created_items.extend(items)
        return list(items)

    repository.create_or_get_prediction_batch.side_effect = create_batch
    repository.add_prediction_batch_items.side_effect = add_batch_items
    repository.update_prediction_batch_item.side_effect = update_item

    async def get_batch(batch_id: str, _org_id: str):
        assert created_batch is not None
        items = [stored_items.get(item.id, item) for item in created_items]
        return created_batch, items

    repository.get_prediction_batch.side_effect = get_batch
    prediction_execution = AsyncMock()
    prediction_execution.submit_job.return_value = SimpleNamespace(
        id="prediction-new", status=JobStatus.QUEUED
    )
    service = CollectionModelAutomationService(
        repository=repository,
        model_catalog=AsyncMock(),
        prediction_execution=prediction_execution,
        dataset_revisions=_dataset_revisions(
            **{
                "dataset-old": "revision-old",
                "dataset-covered": "revision-covered",
                "dataset-new": "revision-new",
            }
        ),
    )

    batch = await service.predict_new_members(
        "collection-1", "revision-2", "org-1", "user-1"
    )

    assert batch is not None
    assert [item.dataset_id for item in created_items] == ["dataset-new"]
    command = prediction_execution.submit_job.await_args.args[0]
    assert command.dataset_id == "dataset-new"
    assert command.collection_id == "collection-1"
    assert command.collection_revision_id == "revision-2"
    assert command.collection_member_id == "member-new"
    assert command.submission_origin.value == "automation"


@pytest.mark.asyncio
async def test_coverage_uses_latest_success_and_exposes_active_run() -> None:
    revision = _revision(2, ("member-1", "dataset-1", "revision-current"))
    now = _now()
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.get_revision.return_value = revision
    repository.list_prediction_observations.return_value = [
        CollectionPredictionObservation(
            member_id="member-1",
            dataset_id="dataset-1",
            prediction_job_id="job-active",
            dataset_revision_id="revision-current",
            model_id="model-1",
            status=JobStatus.RUNNING.value,
            created_at=now,
        ),
        CollectionPredictionObservation(
            member_id="member-1",
            dataset_id="dataset-1",
            prediction_job_id="job-latest-success",
            dataset_revision_id="revision-current",
            model_id="model-old",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(minutes=1),
        ),
        CollectionPredictionObservation(
            member_id="member-1",
            dataset_id="dataset-1",
            prediction_job_id="job-older-success",
            dataset_revision_id="revision-current",
            model_id="model-1",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(minutes=2),
        ),
    ]
    service = CollectionModelAutomationService(
        repository=repository,
        model_catalog=AsyncMock(),
        prediction_execution=AsyncMock(),
        dataset_revisions=_dataset_revisions(**{"dataset-1": "revision-current"}),
    )

    coverage = await service.list_coverage(
        "collection-1", "org-1", revision_id="revision-2"
    )

    assert coverage[0].status is PredictionCoverageStatus.MODEL_MISMATCH
    assert coverage[0].latest_prediction_job_id == "job-latest-success"
    assert coverage[0].latest_prediction_status == JobStatus.COMPLETED.value
    assert coverage[0].active_prediction_job_id == "job-active"
    assert coverage[0].active_prediction_status == JobStatus.RUNNING.value


@pytest.mark.asyncio
async def test_revision_stays_successful_when_incremental_preparation_fails() -> None:
    revision = _revision(1, ("member-1", "dataset-1", "revision-1"))
    collections = AsyncMock()
    collections.create_revision.return_value = revision
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.list_prediction_batches.return_value = []
    repository.get_revision.return_value = revision
    repository.get_current_revision.return_value = revision
    repository.list_revisions.return_value = [revision]
    repository.create_or_get_prediction_batch.side_effect = (
        lambda batch, items, _org_id: (batch, list(items), True)
    )
    dataset_revisions = AsyncMock()
    dataset_revisions.list_current.side_effect = RuntimeError(
        "dataset revision service unavailable"
    )
    automation = CollectionModelAutomationService(
        repository=repository,
        model_catalog=AsyncMock(),
        prediction_execution=AsyncMock(),
        dataset_revisions=dataset_revisions,
    )
    publisher = CollectionRevisionPublishingService(
        collections, AsyncMock(), automation
    )

    result = await publisher.create_revision(
        "collection-1",
        "org-1",
        actor_id="user-1",
        expected_definition_version=1,
        trigger_kind="manual",
        trigger_ref=None,
    )

    assert result is revision
    created_batch, created_items, created_org_id = (
        repository.create_or_get_prediction_batch.await_args.args
    )
    assert created_batch.collection_revision_id == revision.id
    assert created_batch.kind == "incremental"
    assert created_batch.request_id == revision.id
    assert created_batch.status == "pending"
    assert created_items == ()
    assert created_org_id == "org-1"
    repository.update_prediction_batch_status.assert_awaited_once_with(
        created_batch.id,
        "failed",
    )


@pytest.mark.asyncio
async def test_retry_reprepares_failed_incremental_batch_on_manual_queue() -> None:
    revision = _revision(1, ("member-1", "dataset-1", "revision-1"))
    now = _now()
    batch = CollectionPredictionBatch(
        id="batch-1",
        collection_id="collection-1",
        collection_revision_id=revision.id,
        model_id="model-1",
        kind="incremental",
        request_id=revision.id,
        status="failed",
        created_by="user-1",
        created_at=now,
        updated_at=now,
    )
    repository = AsyncMock()
    repository.get_collection.return_value = _collection()
    repository.get_revision.return_value = revision
    repository.get_current_revision.return_value = revision
    repository.list_revisions.return_value = [revision]
    repository.list_prediction_observations.return_value = []
    stored_items: list[CollectionPredictionBatchItem] = []

    async def get_batch(_batch_id: str, _org_id: str):
        return batch, list(stored_items)

    async def add_items(_batch_id: str, items):
        stored_items.extend(items)
        return list(items)

    async def update_item(item_id: str, **updates: object):
        item = next(candidate for candidate in stored_items if candidate.id == item_id)
        stored_items[0] = CollectionPredictionBatchItem(
            id=item.id,
            batch_id=item.batch_id,
            member_id=item.member_id,
            dataset_id=item.dataset_id,
            dataset_revision_id=item.dataset_revision_id,
            prediction_job_id=str(updates["prediction_job_id"]),
            status=str(updates["status"]),
            attempt_count=1,
            error_detail=None,
            created_at=item.created_at,
            updated_at=_now(),
        )
        return stored_items[0]

    repository.get_prediction_batch.side_effect = get_batch
    repository.add_prediction_batch_items.side_effect = add_items
    repository.update_prediction_batch_item.side_effect = update_item
    prediction_execution = AsyncMock()
    prediction_execution.submit_job.return_value = SimpleNamespace(
        id="prediction-retry",
        status=JobStatus.QUEUED,
    )
    service = CollectionModelAutomationService(
        repository=repository,
        model_catalog=AsyncMock(),
        prediction_execution=prediction_execution,
        dataset_revisions=_dataset_revisions(**{"dataset-1": "revision-1"}),
    )

    retried_batch, retried_items = await service.retry_batch(
        batch.id,
        "org-1",
        actor_id="user-1",
    )

    assert retried_batch.id == batch.id
    assert [item.dataset_id for item in retried_items] == ["dataset-1"]
    command = prediction_execution.submit_job.await_args.args[0]
    assert command.collection_prediction_batch_id == batch.id
    assert command.submission_origin is PredictionSubmissionOrigin.MANUAL


@pytest.mark.asyncio
async def test_repository_adds_prepared_items_to_durable_empty_batch() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        now = _now()
        session_factory = create_session_factory(engine)
        repository = DatasetCollectionSqlRepository(session_factory)
        async with session_factory() as session:
            session.add(OrganizationORM(id="org-1", name="Org", slug="org-1"))
            session.add(
                DatasetCollectionORM(
                    id="collection-1",
                    org_id="org-1",
                    name="Collection",
                    description="",
                    target_view_id="patch_image_v1",
                    target_view_contract="sc.patch-image",
                    target_schema_version="1",
                    duplicate_policy="keep_all",
                    missing_data_policy="fail",
                    definition_version=1,
                    created_by="user-1",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                CollectionPredictionBatchORM(
                    id="batch-1",
                    collection_id="collection-1",
                    collection_revision_id="revision-1",
                    model_id="model-1",
                    kind="incremental",
                    request_id="revision-1",
                    status="failed",
                    created_by="user-1",
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        item = CollectionPredictionBatchItem(
            id="item-1",
            batch_id="batch-1",
            member_id="member-1",
            dataset_id="dataset-1",
            dataset_revision_id="dataset-revision-1",
            prediction_job_id=None,
            status="pending",
            attempt_count=0,
            error_detail=None,
            created_at=now,
            updated_at=now,
        )

        created = await repository.add_prediction_batch_items("batch-1", (item,))
        replayed = await repository.add_prediction_batch_items("batch-1", (item,))
        stored = await repository.get_prediction_batch("batch-1", "org-1")

        assert created == [item]
        assert [candidate.id for candidate in replayed] == [item.id]
        assert stored is not None
        stored_batch, stored_items = stored
        assert stored_batch.status == "pending"
        assert [candidate.id for candidate in stored_items] == [item.id]
    finally:
        await engine.dispose()
