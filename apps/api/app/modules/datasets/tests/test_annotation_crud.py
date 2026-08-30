from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.shared.api.schemas import Organization, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["rose", "tulip"]}
_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def _create_dataset_and_sample(c: TestClient) -> tuple[str, str]:
    """Create a dataset and one sample, return (dataset_id, sample_id)."""
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "ann-test-ds", "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    sample = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []})
    assert sample.status_code == 200
    return dataset_id, sample.json()["id"]


def _create_annotation(c: TestClient, sample_id: str, dataset_id: str, label: str = "rose") -> str:
    r = c.post(
        "/api/v1/annotations",
        json={"dataset_id": dataset_id, "sample_id": sample_id, "label": label, "created_by": "tester"},
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_single_annotation_does_not_mutate_configured_label_space() -> None:
    import datetime

    from app.modules.auth.port.http.deps import get_current_org, get_current_user
    from app.modules.datasets.port.http.deps import (
        get_label_studio_client as datasets_get_ls_client,
    )

    # -- mock auth --
    _mock_user = User(
        id=_DEFAULT_USER_ID,
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime.datetime(2024, 1, 1),
    )
    _mock_org = Organization(
        id=_DEFAULT_ORG_ID,
        name="Default",
        slug="default",
        created_at=datetime.datetime(2024, 1, 1),
    )
    app.dependency_overrides[get_current_user] = lambda: _mock_user
    app.dependency_overrides[get_current_org] = lambda: _mock_org

    # -- mock LS client --
    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    app.dependency_overrides[datasets_get_ls_client] = lambda: _mock_ls

    try:
        with TestClient(app) as c:
            # -- create dataset with label_space ["cat", "dog"] --
            ds_resp = c.post(
                "/api/v1/datasets",
                json={
                    "name": "expand-test-ds",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat", "dog"],
                    },
                },
            )
            assert ds_resp.status_code == 200, ds_resp.text
            dataset_id = ds_resp.json()["id"]

            # -- create a sample (gets ls_task_id from mock LS) --
            sample_resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={})
            assert sample_resp.status_code == 200, sample_resp.text
            sample_id = sample_resp.json()["id"]

            # -- create a single annotation with a NEW label "bird" --
            ann_resp = c.post(
                "/api/v1/annotations",
                json={"dataset_id": dataset_id, "sample_id": sample_id, "label": "bird"},
            )
            assert ann_resp.status_code == 200, ann_resp.text

            # -- fetch dataset and check label_space --
            ds_resp2 = c.get(f"/api/v1/datasets/{dataset_id}")
            assert ds_resp2.status_code == 200, ds_resp2.text
            label_space = ds_resp2.json()["task_spec"]["label_space"]

            assert label_space == ["cat", "dog"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_org, None)
        app.dependency_overrides.pop(datasets_get_ls_client, None)


# ---------------------------------------------------------------------------
# Test 1: List annotations for sample (empty)
# ---------------------------------------------------------------------------


def test_list_annotations_empty() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)

        resp = c.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 2: List annotations for sample (with data)
# ---------------------------------------------------------------------------


def test_list_annotations_with_data() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        _create_annotation(c, sample_id, dataset_id, label="rose")

        resp = c.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["label"] == "rose"
        assert body[0]["sample_id"] == sample_id


# ---------------------------------------------------------------------------
# Test 3: Update annotation label
# ---------------------------------------------------------------------------


def test_update_annotation_label() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id, label="rose")

        resp = c.patch(f"/api/v1/annotations/{ann_id}", json={"dataset_id": dataset_id, "label": "tulip"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "tulip"
        assert resp.json()["id"] == ann_id


def test_annotation_overwrite_does_not_mutate_configured_label_space() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id, label="temporary")

        response = c.patch(
            f"/api/v1/annotations/{ann_id}",
            json={"dataset_id": dataset_id, "label": "rose"},
        )
        assert response.status_code == 200, response.text

        annotations = c.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert annotations.status_code == 200, annotations.text
        assert [item["label"] for item in annotations.json()] == ["rose"]

        stats = c.get(f"/api/v1/datasets/{dataset_id}/annotation-stats")
        assert stats.status_code == 200, stats.text
        assert stats.json()["label_counts"] == {"rose": 1}

        dataset = c.get(f"/api/v1/datasets/{dataset_id}")
        assert dataset.status_code == 200, dataset.text
        assert dataset.json()["task_spec"]["label_space"] == ["rose", "tulip"]


# ---------------------------------------------------------------------------
# Test 3b: Update annotation — label_space MUST NOT auto-expand
# ---------------------------------------------------------------------------


def test_update_annotation_does_not_mutate_configured_label_space() -> None:
    import datetime

    from app.modules.auth.port.http.deps import get_current_org, get_current_user
    from app.modules.datasets.port.http.deps import (
        get_label_studio_client as datasets_get_ls_client,
    )

    # -- mock auth --
    _mock_user = User(
        id=_DEFAULT_USER_ID,
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime.datetime(2024, 1, 1),
    )
    _mock_org = Organization(
        id=_DEFAULT_ORG_ID,
        name="Default",
        slug="default",
        created_at=datetime.datetime(2024, 1, 1),
    )
    app.dependency_overrides[get_current_user] = lambda: _mock_user
    app.dependency_overrides[get_current_org] = lambda: _mock_org

    # -- mock LS client --
    _mock_ls = MagicMock()
    _mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "mock-project"})
    _mock_ls.create_task = AsyncMock(return_value={"id": 1})
    _mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    app.dependency_overrides[datasets_get_ls_client] = lambda: _mock_ls

    try:
        with TestClient(app) as c:
            # -- create dataset with label_space ["cat", "dog"] --
            ds_resp = c.post(
                "/api/v1/datasets",
                json={
                    "name": "update-expand-test-ds",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat", "dog"],
                    },
                },
            )
            assert ds_resp.status_code == 200, ds_resp.text
            dataset_id = ds_resp.json()["id"]

            # -- create a sample (gets ls_task_id from mock LS) --
            sample_resp = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={})
            assert sample_resp.status_code == 200, sample_resp.text
            sample_id = sample_resp.json()["id"]

            # -- create an annotation with existing label "cat" --
            ann_resp = c.post(
                "/api/v1/annotations",
                json={"dataset_id": dataset_id, "sample_id": sample_id, "label": "cat"},
            )
            assert ann_resp.status_code == 200, ann_resp.text
            ann_id = ann_resp.json()["id"]

            # -- update annotation to a NEW label "bird" via PATCH --
            patch_resp = c.patch(f"/api/v1/annotations/{ann_id}", json={"dataset_id": dataset_id, "label": "bird"})
            assert patch_resp.status_code == 200, patch_resp.text
            assert patch_resp.json()["label"] == "bird"

            # -- fetch dataset and check label_space --
            ds_resp2 = c.get(f"/api/v1/datasets/{dataset_id}")
            assert ds_resp2.status_code == 200, ds_resp2.text
            label_space = ds_resp2.json()["task_spec"]["label_space"]

            assert label_space == ["cat", "dog"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_org, None)
        app.dependency_overrides.pop(datasets_get_ls_client, None)


# ---------------------------------------------------------------------------
# Test 4: Delete annotation
# ---------------------------------------------------------------------------


def test_delete_annotation() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id)

        resp = c.delete(f"/api/v1/annotations/{ann_id}?dataset_id={dataset_id}")
        assert resp.status_code == 204


def test_annotation_delete_does_not_mutate_configured_label_space() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id, label="temporary")

        response = c.delete(
            f"/api/v1/annotations/{ann_id}?dataset_id={dataset_id}"
        )
        assert response.status_code == 204, response.text

        annotations = c.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert annotations.status_code == 200, annotations.text
        assert annotations.json() == []

        stats = c.get(f"/api/v1/datasets/{dataset_id}/annotation-stats")
        assert stats.status_code == 200, stats.text
        assert stats.json()["label_counts"] == {}

        dataset = c.get(f"/api/v1/datasets/{dataset_id}")
        assert dataset.status_code == 200, dataset.text
        assert dataset.json()["task_spec"]["label_space"] == ["rose", "tulip"]


# ---------------------------------------------------------------------------
# Test 5: Get annotation after delete → 404
# ---------------------------------------------------------------------------


def test_delete_annotation_twice_returns_404() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id)

        # First delete succeeds
        resp1 = c.delete(f"/api/v1/annotations/{ann_id}?dataset_id={dataset_id}")
        assert resp1.status_code == 204

        # Second delete → 404
        resp2 = c.delete(f"/api/v1/annotations/{ann_id}?dataset_id={dataset_id}")
        assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Test 6: Update non-existent annotation → 404
# ---------------------------------------------------------------------------


def test_update_nonexistent_annotation_returns_404() -> None:
    with TestClient(app) as c:
        dataset_id, _sample_id = _create_dataset_and_sample(c)
        resp = c.patch("/api/v1/annotations/nonexistent-id", json={"dataset_id": dataset_id, "label": "tulip"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Delete non-existent annotation → 404
# ---------------------------------------------------------------------------


def test_delete_nonexistent_annotation_returns_404() -> None:
    with TestClient(app) as c:
        dataset_id, _sample_id = _create_dataset_and_sample(c)
        resp = c.delete(f"/api/v1/annotations/nonexistent-id?dataset_id={dataset_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: List annotations for non-existent sample → 404
# ---------------------------------------------------------------------------


def test_list_annotations_nonexistent_sample_returns_404() -> None:
    with TestClient(app) as c:
        resp = c.get(
            "/api/v1/datasets/nonexistent-dataset/samples/"
            "nonexistent-id/annotations"
        )
        assert resp.status_code == 404
