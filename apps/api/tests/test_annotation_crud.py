from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["rose", "tulip"]}


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
        json={"sample_id": sample_id, "label": label, "created_by": "tester"},
    )
    assert r.status_code == 200
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Test 1: List annotations for sample (empty)
# ---------------------------------------------------------------------------


def test_list_annotations_empty() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c)

        resp = c.get(f"/api/v1/samples/{sample_id}/annotations")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Test 2: List annotations for sample (with data)
# ---------------------------------------------------------------------------


def test_list_annotations_with_data() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        _create_annotation(c, sample_id, dataset_id, label="rose")

        resp = c.get(f"/api/v1/samples/{sample_id}/annotations")
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

        resp = c.patch(f"/api/v1/annotations/{ann_id}", json={"label": "tulip"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "tulip"
        assert resp.json()["id"] == ann_id


# ---------------------------------------------------------------------------
# Test 4: Delete annotation
# ---------------------------------------------------------------------------


def test_delete_annotation() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id)

        resp = c.delete(f"/api/v1/annotations/{ann_id}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Test 5: Get annotation after delete → 404
# ---------------------------------------------------------------------------


def test_delete_annotation_twice_returns_404() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)
        ann_id = _create_annotation(c, sample_id, dataset_id)

        # First delete succeeds
        resp1 = c.delete(f"/api/v1/annotations/{ann_id}")
        assert resp1.status_code == 204

        # Second delete → 404
        resp2 = c.delete(f"/api/v1/annotations/{ann_id}")
        assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Test 6: Update non-existent annotation → 404
# ---------------------------------------------------------------------------


def test_update_nonexistent_annotation_returns_404() -> None:
    with TestClient(app) as c:
        resp = c.patch("/api/v1/annotations/nonexistent-id", json={"label": "tulip"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Delete non-existent annotation → 404
# ---------------------------------------------------------------------------


def test_delete_nonexistent_annotation_returns_404() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/annotations/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: List annotations for non-existent sample → 404
# ---------------------------------------------------------------------------


def test_list_annotations_nonexistent_sample_returns_404() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/samples/nonexistent-id/annotations")
        assert resp.status_code == 404
