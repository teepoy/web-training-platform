from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import get_current_user
from app.shared.api.schemas import User
from tests.conftest import create_dataset


def _as_user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id,
        is_superadmin=False,
        created_at=datetime(2024, 1, 1),
    )


def _with_current_user(user: User):
    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    return original


def _restore_current_user(original) -> None:
    if original is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = original


def test_list_datasets_returns_paginated_response() -> None:
    with TestClient(app) as c:
        for index in range(3):
            create_dataset(c, name=f"page-dataset-{index}")

        resp = c.get("/api/v1/datasets?limit=2&offset=1")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"items", "total"}
        assert body["total"] == 3
        assert len(body["items"]) == 2


def test_rename_dataset_requires_creator() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c, name="owner-only-rename")
        original = _with_current_user(_as_user("other-user"))
        try:
            resp = c.patch(
                f"/api/v1/datasets/{dataset_id}",
                json={"name": "should-not-rename"},
            )
        finally:
            _restore_current_user(original)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Only the dataset creator can rename this dataset"


def test_delete_dataset_requires_creator() -> None:
    with TestClient(app) as c:
        dataset_id = create_dataset(c, name="owner-only-delete")
        original = _with_current_user(_as_user("other-user"))
        try:
            resp = c.delete(f"/api/v1/datasets/{dataset_id}")
        finally:
            _restore_current_user(original)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Only the dataset creator can delete this dataset"
