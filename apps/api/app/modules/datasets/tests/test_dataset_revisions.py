from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app
from app.modules.datasets.domain.entities import DatasetRevisionOperation
from tests.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID


def _create_dataset(client: TestClient) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": "revision-history-test",
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": ["cat", "dog"],
            },
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def test_legacy_dataset_revision_history_stays_empty() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client)

        history_response = client.get(f"/api/v1/datasets/{dataset_id}/revisions")
        current_response = client.get(
            f"/api/v1/datasets/{dataset_id}/revisions/current"
        )

    assert history_response.status_code == 200
    assert history_response.json() == {"items": [], "total": 0}
    assert current_response.status_code == 404
    assert current_response.json() == {"detail": "Dataset revision not found"}


def test_publish_sparse_revision_archives_manifest_and_updates_history() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/datasets",
            json={
                "name": "completed-import",
                "dataset_type": "image_sc",
                "task_spec": {"task_type": "sc", "label_space": []},
                "storage_mode": "file_shard_sparse",
            },
        )
        assert response.status_code == 200, response.text
        dataset_id = str(response.json()["id"])
        revisions = app.state.app_context.datasets.dataset_revision_service

        first = asyncio.run(
            revisions.publish_sparse_revision(
                dataset_id=dataset_id,
                org_id="00000000-0000-0000-0000-000000000001",
                operation=DatasetRevisionOperation.INITIAL_IMPORT,
                created_by="00000000-0000-0000-0000-000000000002",
                provenance={"source": "test-fixture"},
            )
        )
        second = asyncio.run(
            revisions.publish_sparse_revision(
                dataset_id=dataset_id,
                org_id="00000000-0000-0000-0000-000000000001",
                operation=DatasetRevisionOperation.REIMPORT,
                operation_ref="import-run-2",
                created_by="00000000-0000-0000-0000-000000000002",
                provenance={"source": "test-fixture", "version": "2"},
            )
        )

        current_response = client.get(
            f"/api/v1/datasets/{dataset_id}/revisions/current"
        )
        history_response = client.get(f"/api/v1/datasets/{dataset_id}/revisions")

    assert first.revision_number == 1
    assert first.manifest_uri.endswith(
        f"/{dataset_id}/revisions/{first.id}/manifest.json"
    )
    assert second.revision_number == 2
    assert current_response.status_code == 200
    assert current_response.json()["id"] == second.id
    assert current_response.json()["operation_ref"] == "import-run-2"
    assert current_response.json()["is_reproducible"] is False
    assert history_response.status_code == 200
    assert history_response.json()["total"] == 2
    assert [item["revision_number"] for item in history_response.json()["items"]] == [
        2,
        1,
    ]


def test_first_revision_aware_consumer_creates_lightweight_audit_baseline() -> None:
    with TestClient(app) as client:
        dataset_id = _create_dataset(client)
        revisions = app.state.app_context.datasets.dataset_revision_service

        first = asyncio.run(
            revisions.resolve_or_create_baseline(
                dataset_id=dataset_id,
                org_id=DEFAULT_ORG_ID,
                created_by=DEFAULT_USER_ID,
            )
        )
        second = asyncio.run(
            revisions.resolve_or_create_baseline(
                dataset_id=dataset_id,
                org_id=DEFAULT_ORG_ID,
                created_by=DEFAULT_USER_ID,
            )
        )
        raw_manifest = asyncio.run(
            app.state.app_context.shared.artifact_storage.get_bytes(
                first.manifest_uri
            )
        )
        materialized_uris = asyncio.run(
            app.state.app_context.shared.artifact_storage.list_prefix(
                f"materialized/{dataset_id}/"
            )
        )

    manifest = json.loads(raw_manifest)
    assert second.id == first.id
    assert first.revision_number == 1
    assert first.operation == DatasetRevisionOperation.LEGACY_BASELINE
    assert first.is_reproducible is False
    assert manifest["manifest_schema_version"] == (
        "dataset-revision-audit-manifest.v1"
    )
    assert manifest["dataset_id"] == dataset_id
    assert manifest["storage_mode"] == "db_full"
    assert manifest["is_reproducible"] is False
    assert manifest["source_reference"] == {
        "kind": "database_current",
        "dataset_id": dataset_id,
    }
    assert materialized_uris == []


def test_current_revisions_are_loaded_in_one_query_for_many_datasets() -> None:
    with TestClient(app) as client:
        dataset_ids = tuple(_create_dataset(client) for _ in range(6))
        revisions = app.state.app_context.datasets.dataset_revision_service
        for dataset_id in dataset_ids:
            asyncio.run(
                revisions.resolve_or_create_baseline(
                    dataset_id=dataset_id,
                    org_id=DEFAULT_ORG_ID,
                    created_by=DEFAULT_USER_ID,
                )
            )

        statements: list[str] = []

        def record_statement(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            statements.append(statement)

        engine = app.state.app_context.shared.db_engine.sync_engine
        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            current = asyncio.run(
                revisions.list_current(dataset_ids, DEFAULT_ORG_ID)
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

    assert set(current) == set(dataset_ids)
    assert len(statements) == 1
