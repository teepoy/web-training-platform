from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import app


def test_persist_entire_collection_creates_dataset():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "persist-test"})
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp2 = c.post(f"/api/v1/preview-sessions/{session_id}/persist", json={"scope": "entire_collection"})
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"
        assert data["dataset_id"]
        assert data["imported_count"] > 0
        assert data["error"] is None

        dataset_id = data["dataset_id"]
        resp3 = c.get(f"/api/v1/datasets/{dataset_id}")
        assert resp3.status_code == 200
        assert resp3.json()["id"] == dataset_id


def test_persist_idempotent():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "idempotent-test"})
        session_id = resp.json()["session_id"]

        resp1 = c.post(f"/api/v1/preview-sessions/{session_id}/persist", json={"scope": "loaded_items_only"})
        assert resp1.status_code == 200
        dataset_id_1 = resp1.json()["dataset_id"]

        resp2 = c.post(f"/api/v1/preview-sessions/{session_id}/persist", json={"scope": "loaded_items_only"})
        assert resp2.status_code == 200
        assert resp2.json()["dataset_id"] == dataset_id_1


def test_persist_status_endpoint():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "status-test"})
        session_id = resp.json()["session_id"]
        c.post(f"/api/v1/preview-sessions/{session_id}/persist", json={"scope": "loaded_items_only"})

        resp2 = c.get(f"/api/v1/preview-sessions/{session_id}/persist-status")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"


def test_persist_status_404_before_persist():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "no-persist-test"})
        session_id = resp.json()["session_id"]

        resp2 = c.get(f"/api/v1/preview-sessions/{session_id}/persist-status")
        assert resp2.status_code == 404


def test_persist_loaded_items_only():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "loaded-only-test"})
        session_id = resp.json()["session_id"]

        c.get(f"/api/v1/preview-sessions/{session_id}/items", params={"limit": 3})

        resp2 = c.post(
            f"/api/v1/preview-sessions/{session_id}/persist",
            json={"scope": "loaded_items_only"},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"
        assert data["imported_count"] > 0
        assert data["dataset_id"]


def test_persist_invalid_scope():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "invalid-scope-test"})
        session_id = resp.json()["session_id"]

        resp2 = c.post(
            f"/api/v1/preview-sessions/{session_id}/persist",
            json={"scope": "not_a_valid_scope"},
        )
        assert resp2.status_code == 422


def test_persist_expired_session():
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/preview-sessions/nonexistent-xyz/persist",
            json={"scope": "entire_collection"},
        )
        assert resp.status_code == 404
