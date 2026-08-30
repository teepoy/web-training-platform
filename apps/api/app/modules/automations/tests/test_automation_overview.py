from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import app
from app.modules.automations.adapter import AutomationOverviewSqlRepository
from app.modules.automations.app.services import AutomationOverviewService
from app.shared.db.registry import Base, OrganizationORM
from app.shared.db.models.dataset_collections import (
    CollectionPredictionBatchItemORM,
    CollectionPredictionBatchORM,
    DatasetCollectionORM,
)
from app.shared.db.models.source_discovery import CollectionDiscoveryRunORM
from app.shared.db.models.prediction import PredictionJobORM
from app.shared.db.session import create_session_factory
from conftest import DEFAULT_ORG_ID


def _collection(collection_id: str, org_id: str, name: str) -> DatasetCollectionORM:
    return DatasetCollectionORM(
        id=collection_id,
        org_id=org_id,
        name=name,
        description="",
        target_view_id="labeled_image_v1",
        target_view_contract="labeled_image_v1@1",
        target_schema_version="1",
        duplicate_policy="keep_first",
        missing_data_policy="exclude",
        definition_version=1,
        created_by="user-1",
    )


@pytest.mark.asyncio
async def test_overview_uses_fixed_query_count_and_filters_unified_runs() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        session_factory = create_session_factory(engine)
        repository = AutomationOverviewSqlRepository(session_factory)
        service = AutomationOverviewService(repository)
        org_id = str(uuid4())
        other_org_id = str(uuid4())
        collection_id = str(uuid4())
        other_collection_id = str(uuid4())
        now = datetime.now(UTC)

        async with session_factory() as session:
            session.add_all(
                [
                    OrganizationORM(id=org_id, name="Overview Org", slug=f"overview-{org_id}"),
                    OrganizationORM(
                        id=other_org_id,
                        name="Other Org",
                        slug=f"other-{other_org_id}",
                    ),
                    _collection(collection_id, org_id, "Incoming wafer review"),
                    _collection(other_collection_id, other_org_id, "Hidden collection"),
                ]
            )
            for index in range(12):
                session.add(
                    CollectionDiscoveryRunORM(
                        id=f"discovery-{index}",
                        org_id=org_id,
                        collection_id=collection_id,
                        rule_id=f"rule-{index}",
                        rule_version_id=f"rule-version-{index}",
                        kind="backfill" if index == 0 else "live",
                        status="needs_attention" if index == 0 else "completed",
                        as_of_utc=now,
                        stats={},
                        error_detail="One record failed" if index == 0 else None,
                        created_by="user-1",
                        created_at=now - timedelta(minutes=index),
                        completed_at=now,
                    )
            )
            for index in range(12):
                batch_id = "fresh-job-batch" if index == 1 else f"prediction-{index}"
                session.add(
                    CollectionPredictionBatchORM(
                        id=batch_id,
                        collection_id=collection_id,
                        collection_revision_id=f"snapshot-{index}",
                        model_id=f"model-{index}",
                        kind="incremental",
                        request_id=f"request-{index}",
                        status="pending",
                        created_by="user-1",
                        created_at=now - timedelta(hours=index),
                        updated_at=now,
                    )
                )
                session.add(
                    CollectionPredictionBatchItemORM(
                        id=f"prediction-item-{index}",
                        batch_id=batch_id,
                        member_id=f"member-{index}",
                        dataset_id=f"dataset-{index}",
                        dataset_revision_id=f"dataset-revision-{index}",
                        prediction_job_id="job-1" if index == 1 else None,
                        status=(
                            "failed" if index == 0 else "queued" if index == 1 else "completed"
                        ),
                        attempt_count=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                if index == 1:
                    session.add(
                        PredictionJobORM(
                            id="job-1",
                            org_id=org_id,
                            dataset_id="dataset-1",
                            model_id="model-1",
                            status="completed",
                            target="image_classification",
                            summary_json={},
                            created_by="user-1",
                            created_at=now - timedelta(hours=1),
                            updated_at=now + timedelta(minutes=1),
                        )
                    )
            session.add(
                CollectionPredictionBatchORM(
                    id="preparation-failed-batch",
                    collection_id=collection_id,
                    collection_revision_id="preparation-failed-revision",
                    model_id="preparation-failed-model",
                    kind="incremental",
                    request_id="preparation-failed-revision",
                    status="failed",
                    created_by="user-1",
                    created_at=now + timedelta(minutes=1),
                    updated_at=now + timedelta(minutes=2),
                )
            )
            session.add(
                CollectionDiscoveryRunORM(
                    id="other-run",
                    org_id=other_org_id,
                    collection_id=other_collection_id,
                    rule_id="other-rule",
                    rule_version_id="other-rule-version",
                    kind="live",
                    status="completed",
                    as_of_utc=now,
                    stats={},
                    created_by="other-user",
                    created_at=now,
                    completed_at=now,
                )
            )
            await session.commit()

        select_count = 0

        def count_selects(_conn, _cursor, statement, *_args) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            items, total = await service.list_runs(
                org_id,
                offset=0,
                limit=10,
                status=None,
                recipe_kind=None,
                query=None,
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

        assert total == 25
        assert len(items) == 10
        assert select_count == 2
        assert {item.target_label for item in items} == {"Incoming wafer review"}

        attention, attention_total = await service.list_runs(
            org_id,
            offset=0,
            limit=50,
            status="needs_attention",
            recipe_kind=None,
            query="wafer",
        )
        assert attention_total == 3
        assert {item.recipe_kind for item in attention} == {"backfill", "prediction"}
        retry_by_kind = {item.recipe_kind: item.retry_supported for item in attention}
        assert retry_by_kind == {"backfill": False, "prediction": True}
        preparation_failure = next(
            item for item in attention if item.id == "preparation-failed-batch"
        )
        assert preparation_failure.status == "failed"
        assert preparation_failure.retry_supported is True
        assert preparation_failure.detail == (
            "Prediction preparation failed before child jobs were created"
        )

        refreshed, refreshed_total = await service.list_runs(
            org_id,
            offset=0,
            limit=10,
            status="completed",
            recipe_kind="prediction",
            query="fresh-job-batch",
        )
        assert refreshed_total == 1
        assert refreshed[0].status == "completed"
        assert refreshed[0].completed_at == now + timedelta(minutes=1)
    finally:
        await engine.dispose()


def test_automation_overview_route_is_paginated_and_rejects_unknown_filters() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/automations?limit=25")
        invalid = client.get("/api/v1/automations?kind=arbitrary-workflow")

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0}
    assert invalid.status_code == 422


def test_automation_overview_is_scoped_to_current_organization() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/automations",
            headers={"X-Organization-ID": DEFAULT_ORG_ID},
        )

    assert response.status_code == 200, response.text
