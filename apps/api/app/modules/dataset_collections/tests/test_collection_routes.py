from __future__ import annotations

import asyncio
from datetime import datetime
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import get_current_user
from app.modules.dataset_collections.port.local import CollectionPredictionAutomationPort
from app.modules.datasets.domain.entities import DatasetRevisionOperation
from app.shared.api.schemas import User
from tests.conftest import (
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    TRAINER_ID,
    create_job,
    upload_model,
)


def _create_sc_dataset(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": "image_sc",
            "task_spec": {
                "task_type": "sc",
                "label_space": ["clean", "defect"],
            },
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _create_sc_sample(client: TestClient, dataset_id: str) -> None:
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/samples",
        json={
            "image_uris": [],
            "metadata": {
                "sample_id": "upstream-42",
                "inspection_time": "2026-08-05T08:00:00",
                "wafer_key": 1,
                "defect_id": "42",
                "wafer_x": 0,
                "wafer_y": 0,
            },
        },
    )
    assert response.status_code == 200, response.text


def _as_user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        is_superadmin=False,
        created_at=datetime(2024, 1, 1),
    )


def test_list_collections_sorts_before_pagination() -> None:
    with TestClient(app) as client:
        for name in ("Zulu collection", "Alpha collection"):
            response = client.post(
                "/api/v1/dataset-collections",
                json={
                    "name": name,
                    "description": "sorting fixture",
                    "target_view_id": "patch_image_v1",
                    "duplicate_policy": "keep_all",
                    "missing_data_policy": "fail",
                },
            )
            assert response.status_code == 200, response.text

        response = client.get(
            "/api/v1/dataset-collections?sort_by=name&sort_order=asc&limit=1"
        )

        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert [item["name"] for item in response.json()["items"]] == [
            "Alpha collection"
        ]
        assert (
            client.get("/api/v1/dataset-collections?sort_by=unknown").status_code
            == 422
        )


def test_collection_members_can_be_linked_and_unlinked_dynamically() -> None:
    with TestClient(app) as client:
        first_dataset = _create_sc_dataset(client, "inspection one")
        second_dataset = _create_sc_dataset(client, "inspection two")
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Line A stack",
                "description": "Two imported inspections",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        assert created.status_code == 200, created.text
        collection = created.json()
        collection_id = str(collection["id"])
        assert collection["definition_version"] == 0

        linked = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [
                    {"source_dataset_id": first_dataset, "position": 0},
                    {"source_dataset_id": second_dataset, "position": 1},
                ],
            },
        )
        assert linked.status_code == 200, linked.text
        membership = linked.json()
        assert membership["collection"]["definition_version"] == 1
        assert [item["source_dataset_id"] for item in membership["members"]] == [
            first_dataset,
            second_dataset,
        ]

        stale = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [
                    {"source_dataset_id": first_dataset, "position": 2},
                ],
            },
        )
        assert stale.status_code in {409, 422}

        member_id = str(membership["members"][0]["id"])
        unlinked = client.delete(
            f"/api/v1/dataset-collections/{collection_id}/members/{member_id}",
            params={"expected_definition_version": 1},
        )
        assert unlinked.status_code == 200, unlinked.text
        after = unlinked.json()
        assert after["collection"]["definition_version"] == 2
        assert [item["source_dataset_id"] for item in after["members"]] == [
            second_dataset
        ]


def test_collection_revision_is_immutable_and_ready() -> None:
    with TestClient(app) as client:
        dataset_id = _create_sc_dataset(client, "revision source")
        _create_sc_sample(client, dataset_id)
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Revision source stack",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        collection_id = str(created.json()["id"])
        linked = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [{"source_dataset_id": dataset_id, "position": 0}],
            },
        )
        assert linked.status_code == 200, linked.text
        revision = client.post(
            f"/api/v1/dataset-collections/{collection_id}/revisions",
            json={"expected_definition_version": 1},
        )
        assert revision.status_code == 200, revision.text
        payload = revision.json()
        assert payload["status"] == "ready"
        assert payload["definition_version"] == 1
        assert payload["row_count"] is None
        assert payload["manifest_uri"]
        assert payload["provenance_uri"] is None
        assert payload["manifest_format"] == "collection-composite-observed.v1"
        assert payload["source_resolution"] == "observed"
        assert payload["reproducibility_capability"] is False
        assert len(payload["source_snapshot"]) == 1
        source = payload["source_snapshot"][0]
        assert source["source_dataset_id"] == dataset_id
        assert source["dataset_revision_id"]
        assert source["dataset_revision_number"] == 1
        assert source["dataset_revision_manifest_uri"]
        assert source["dataset_revision_binding"] == "observed"
        assert source["dataset_revision_reproducible"] is False
        assert source["collection_definition_version"] == 1
        assert source["filter_version"]
        assert source["mapping_version"]
        assert source["sampling_version"]

        stored_manifest = json.loads(
            asyncio.run(
                app.state.app_context.shared.artifact_storage.get_bytes(
                    payload["manifest_uri"]
                )
            )
        )
        assert stored_manifest["manifest_format"] == (
            "collection-composite-observed.v1"
        )
        assert stored_manifest["source_resolution"] == "observed"
        assert stored_manifest["reproducibility"]["capability"] is False
        assert stored_manifest["members"] == payload["source_snapshot"]
        assert all(
            not str(value).endswith(("data.parquet", "provenance.parquet"))
            for value in stored_manifest.values()
            if isinstance(value, str)
        )

        unchanged = client.post(
            f"/api/v1/dataset-collections/{collection_id}/revisions",
            json={"expected_definition_version": 1},
        )
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["id"] == payload["id"]
        history = client.get(f"/api/v1/dataset-collections/{collection_id}/revisions")
        assert history.status_code == 200, history.text
        assert [item["id"] for item in history.json()] == [payload["id"]]

        deleted = client.delete(f"/api/v1/dataset-collections/{collection_id}")
        assert deleted.status_code == 204, deleted.text
        missing = client.get(f"/api/v1/dataset-collections/{collection_id}")
        assert missing.status_code == 404, missing.text


def test_collection_refresh_advances_changed_revisions_once_without_prediction() -> None:
    with TestClient(app) as client:
        dataset = client.post(
            "/api/v1/datasets",
            json={
                "name": "refresh source",
                "dataset_type": "image_sc",
                "task_spec": {
                    "task_type": "sc",
                    "label_space": ["clean", "defect"],
                },
                "storage_mode": "file_shard_sparse",
            },
        )
        assert dataset.status_code == 200, dataset.text
        dataset_id = str(dataset.json()["id"])
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Refresh status collection",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        collection_id = str(created.json()["id"])
        linked = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [{"source_dataset_id": dataset_id, "position": 0}],
            },
        )
        assert linked.status_code == 200, linked.text
        initial = client.post(
            f"/api/v1/dataset-collections/{collection_id}/revisions",
            json={"expected_definition_version": 1},
        )
        assert initial.status_code == 200, initial.text
        initial_snapshot = initial.json()
        dataset_revisions = app.state.app_context.datasets.dataset_revision_service
        current_dataset_revision = asyncio.run(
            dataset_revisions.publish_sparse_revision(
                dataset_id=dataset_id,
                org_id=DEFAULT_ORG_ID,
                operation=DatasetRevisionOperation.BATCH_EDIT,
                created_by=DEFAULT_USER_ID,
                provenance={"reason": "refresh-test"},
            )
        )

        status = client.get(
            f"/api/v1/dataset-collections/{collection_id}/snapshot-update-status"
        )
        assert status.status_code == 200, status.text
        assert status.json()["update_available"] is True
        assert status.json()["outdated_member_count"] == 1
        member_status = status.json()["members"][0]
        assert member_status["observed_dataset_revision_id"] == (
            initial_snapshot["source_snapshot"][0]["dataset_revision_id"]
        )
        assert member_status["current_dataset_revision_id"] == current_dataset_revision.id

        assert app.state.app_context.injector is not None
        prediction_automation = app.state.app_context.injector.get(
            CollectionPredictionAutomationPort
        )
        dispatch = AsyncMock()
        with patch.object(prediction_automation, "predict_new_members", new=dispatch):
            refreshed = client.post(
                f"/api/v1/dataset-collections/{collection_id}/refresh-snapshot",
                json={"expected_definition_version": 1},
            )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["outcome"] == "refreshed"
        refreshed_snapshot = refreshed.json()["snapshot"]
        assert refreshed_snapshot["id"] != initial_snapshot["id"]
        assert refreshed_snapshot["source_snapshot"][0]["dataset_revision_id"] == (
            current_dataset_revision.id
        )
        assert dispatch.await_count == 0

        unchanged = client.post(
            f"/api/v1/dataset-collections/{collection_id}/refresh-snapshot",
            json={"expected_definition_version": 1},
        )
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["outcome"] == "unchanged"
        assert unchanged.json()["snapshot"]["id"] == refreshed_snapshot["id"]
        history = client.get(
            f"/api/v1/dataset-collections/{collection_id}/revisions"
        )
        assert history.status_code == 200, history.text
        assert [item["id"] for item in history.json()] == [
            refreshed_snapshot["id"],
            initial_snapshot["id"],
        ]


def test_collection_rejects_unimplemented_member_transforms() -> None:
    with TestClient(app) as client:
        dataset_id = _create_sc_dataset(client, "transform source")
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Transform guard",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        collection_id = str(created.json()["id"])

        linked = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [
                    {
                        "source_dataset_id": dataset_id,
                        "position": 0,
                        "filter_spec": {"rough_bin": [1]},
                    }
                ],
            },
        )

        assert linked.status_code == 422, linked.text
        assert linked.json()["detail"]["code"] == "unsupported_member_transform"


def test_collection_membership_and_revision_mutations_require_creator() -> None:
    with TestClient(app) as client:
        first_dataset = _create_sc_dataset(client, "creator source one")
        second_dataset = _create_sc_dataset(client, "creator source two")
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Creator-owned collection",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        assert created.status_code == 200, created.text
        collection_id = str(created.json()["id"])
        linked = client.post(
            f"/api/v1/dataset-collections/{collection_id}/members",
            json={
                "expected_definition_version": 0,
                "members": [{"source_dataset_id": first_dataset, "position": 0}],
            },
        )
        assert linked.status_code == 200, linked.text
        member_id = str(linked.json()["members"][0]["id"])

        original_override = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: _as_user("other-user")
        try:
            responses = [
                client.post(
                    f"/api/v1/dataset-collections/{collection_id}/members",
                    json={
                        "expected_definition_version": 1,
                        "members": [
                            {"source_dataset_id": second_dataset, "position": 1}
                        ],
                    },
                ),
                client.put(
                    f"/api/v1/dataset-collections/{collection_id}/members",
                    json={
                        "expected_definition_version": 1,
                        "members": [
                            {"source_dataset_id": first_dataset, "position": 0}
                        ],
                    },
                ),
                client.delete(
                    f"/api/v1/dataset-collections/{collection_id}/members/{member_id}",
                    params={"expected_definition_version": 1},
                ),
                client.post(
                    f"/api/v1/dataset-collections/{collection_id}/revisions",
                    json={"expected_definition_version": 1},
                ),
                client.post(
                    f"/api/v1/dataset-collections/{collection_id}/refresh-snapshot",
                    json={"expected_definition_version": 1},
                ),
            ]
        finally:
            if original_override is None:
                app.dependency_overrides.pop(get_current_user, None)
            else:
                app.dependency_overrides[get_current_user] = original_override

        assert [response.status_code for response in responses] == [403, 403, 403, 403, 403]


def test_collection_list_can_filter_by_creator() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "First creator collection",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        assert first.status_code == 200, first.text
        first_creator = str(first.json()["created_by"])

        original_override = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: _as_user("second-creator")
        try:
            second = client.post(
                "/api/v1/dataset-collections",
                json={
                    "name": "Second creator collection",
                    "description": "",
                    "target_view_id": "patch_image_v1",
                    "duplicate_policy": "keep_all",
                    "missing_data_policy": "fail",
                },
            )
        finally:
            if original_override is None:
                app.dependency_overrides.pop(get_current_user, None)
            else:
                app.dependency_overrides[get_current_user] = original_override

        assert second.status_code == 200, second.text
        filtered = client.get(
            "/api/v1/dataset-collections",
            params={"creator_id": "second-creator"},
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert [item["id"] for item in filtered.json()["items"]] == [
            second.json()["id"]
        ]

        first_filtered = client.get(
            "/api/v1/dataset-collections",
            params={"creator_id": first_creator},
        )
        assert first_filtered.status_code == 200, first_filtered.text
        assert all(
            item["created_by"] == first_creator
            for item in first_filtered.json()["items"]
        )


def test_collection_list_can_search_name_description_and_id() -> None:
    with TestClient(app) as client:
        alpha = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Alpha Flowers",
                "description": "Rare alpine samples",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        beta = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Beta Wafers",
                "description": "Production review",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        assert alpha.status_code == 200, alpha.text
        assert beta.status_code == 200, beta.text

        by_name = client.get(
            "/api/v1/dataset-collections",
            params={"q": "alpha flow"},
        )
        assert by_name.status_code == 200, by_name.text
        assert by_name.json()["total"] == 1
        assert [item["id"] for item in by_name.json()["items"]] == [alpha.json()["id"]]

        by_description = client.get(
            "/api/v1/dataset-collections",
            params={"q": "ALPINE"},
        )
        assert by_description.status_code == 200, by_description.text
        assert by_description.json()["total"] == 1
        assert by_description.json()["items"][0]["id"] == alpha.json()["id"]

        by_id = client.get(
            "/api/v1/dataset-collections",
            params={"q": beta.json()["id"]},
        )
        assert by_id.status_code == 200, by_id.text
        assert by_id.json()["total"] == 1
        assert by_id.json()["items"][0]["id"] == beta.json()["id"]


def test_collection_default_model_can_be_set_and_cleared_without_prediction() -> None:
    with TestClient(app) as client:
        dataset_id = _create_sc_dataset(client, "default model source")
        for label in ("clean", "defect"):
            sample = client.post(
                f"/api/v1/datasets/{dataset_id}/samples",
                json={"image_uris": []},
            )
            assert sample.status_code == 200, sample.text
            annotation = client.post(
                "/api/v1/annotations",
                json={
                    "dataset_id": dataset_id,
                    "sample_id": sample.json()["id"],
                    "label": label,
                    "created_by": "tester",
                },
            )
            assert annotation.status_code == 200, annotation.text
        model_id = upload_model(
            client,
            create_job(client, dataset_id, trainer_id=TRAINER_ID),
        )
        created = client.post(
            "/api/v1/dataset-collections",
            json={
                "name": "Default model collection",
                "description": "",
                "target_view_id": "patch_image_v1",
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        assert created.status_code == 200, created.text
        collection_id = str(created.json()["id"])

        set_model = client.patch(
            f"/api/v1/dataset-collections/{collection_id}/default-model",
            json={"expected_binding_version": 0, "model_id": model_id},
        )
        assert set_model.status_code == 200, set_model.text
        assert set_model.json()["default_model_id"] == model_id
        assert set_model.json()["model_binding_version"] == 1
        predictions = client.get(
            "/api/v1/prediction-jobs",
            params={"collection_id": collection_id},
        )
        assert predictions.status_code == 200, predictions.text
        assert predictions.json()["total"] == 0

        cleared = client.patch(
            f"/api/v1/dataset-collections/{collection_id}/default-model",
            json={"expected_binding_version": 1, "model_id": None},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["default_model_id"] is None
        assert cleared.json()["model_binding_version"] == 2
