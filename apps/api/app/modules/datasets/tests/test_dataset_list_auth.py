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
        dataset_ids: set[str] = set()
        for index in range(3):
            dataset_ids.add(create_dataset(c, name=f"page-dataset-{index}"))

        first = c.get("/api/v1/datasets?limit=2&offset=0")
        second = c.get("/api/v1/datasets?limit=2&offset=2")

        assert first.status_code == 200
        assert second.status_code == 200
        first_body = first.json()
        second_body = second.json()
        assert set(first_body) == {"items", "total"}
        assert first_body["total"] == 3
        assert second_body["total"] == 3
        assert len(first_body["items"]) == 2
        assert len(second_body["items"]) == 1
        page_ids = {
            item["id"] for item in [*first_body["items"], *second_body["items"]]
        }
        assert page_ids == dataset_ids


def test_list_datasets_validates_page_bounds() -> None:
    with TestClient(app) as c:
        assert c.get("/api/v1/datasets?limit=0").status_code == 422
        assert c.get("/api/v1/datasets?limit=201").status_code == 422
        assert c.get("/api/v1/datasets?offset=-1").status_code == 422


def test_list_datasets_applies_search_and_creator_before_pagination() -> None:
    with TestClient(app) as c:
        matching_id = create_dataset(c, name="searchable-alpha")
        create_dataset(c, name="unrelated-beta")

        searched = c.get("/api/v1/datasets?limit=1&q=searchable")
        filtered = c.get(
            "/api/v1/datasets?limit=1&creator_id=creator-who-does-not-exist"
        )
        creators = c.get("/api/v1/datasets/creators")

        assert searched.status_code == 200
        assert searched.json()["total"] == 1
        assert [item["id"] for item in searched.json()["items"]] == [matching_id]
        assert filtered.status_code == 200
        assert filtered.json() == {"items": [], "total": 0}
        assert creators.status_code == 200
        assert any(
            creator["id"] == searched.json()["items"][0]["created_by"]
            for creator in creators.json()
        )


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
