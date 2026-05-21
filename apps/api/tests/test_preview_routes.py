from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import app


def test_browse_preview_items():
    from app.shared.db.models import DatasetORM
    from sqlalchemy import select, func
    from app.main import container

    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "test-browse"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert data["classification_enabled"] is False
        assert data["loaded_count"] > 0
        session_id = data["session_id"]

        resp2 = c.get(f"/api/v1/preview-sessions/{session_id}/items", params={"limit": 5})
        assert resp2.status_code == 200
        items_data = resp2.json()
        assert "items" in items_data
        assert "next_cursor" in items_data
        assert "has_more" in items_data

        import asyncio
        repo = container.repository()
        async def _count():
            async with repo.session_factory() as db:
                return await db.scalar(select(func.count()).select_from(DatasetORM))
        count = asyncio.run(_count())
        assert count == 0


def test_expired_session_returns_404():
    with TestClient(app) as c:
        resp = c.get("/api/v1/preview-sessions/nonexistent-session-id")
        assert resp.status_code == 404
        assert "expired or not found" in resp.json()["detail"]

        resp2 = c.get("/api/v1/preview-sessions/nonexistent-session-id/items")
        assert resp2.status_code == 404
        assert "expired or not found" in resp2.json()["detail"]


def test_list_items_pagination():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "paginate-test"})
        session_id = resp.json()["session_id"]

        resp1 = c.get(f"/api/v1/preview-sessions/{session_id}/items", params={"limit": 5})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 5
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        resp2 = c.get(
            f"/api/v1/preview-sessions/{session_id}/items",
            params={"limit": 5, "cursor": data1["next_cursor"]},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 5
        ids1 = {i["upstream_item_id"] for i in data1["items"]}
        ids2 = {i["upstream_item_id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)


def test_get_session_returns_correct_fields():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "fields-test"})
        session_id = resp.json()["session_id"]

        resp2 = c.get(f"/api/v1/preview-sessions/{session_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "session_id" in data
        assert "collection_ref" in data
        assert data["collection_ref"] == "fields-test"
        assert "classification_enabled" in data
        assert data["classification_enabled"] is False
        assert "loaded_count" in data
        assert "has_more" in data


def test_items_limit_boundary():
    with TestClient(app) as c:
        resp = c.post("/api/v1/preview-sessions", json={"collection_ref": "limit-test"})
        session_id = resp.json()["session_id"]

        resp2 = c.get(f"/api/v1/preview-sessions/{session_id}/items", params={"limit": 101})
        assert resp2.status_code == 422
