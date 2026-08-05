from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
                "inspection_time": "2026-08-05T08:00:00",
                "wafer_key": 1,
                "defect_id": "42",
                "wafer_x": 0,
                "wafer_y": 0,
            },
        },
    )
    assert response.status_code == 200, response.text


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
        assert payload["row_count"] == 1
        assert payload["manifest_uri"]
        assert payload["provenance_uri"]


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
