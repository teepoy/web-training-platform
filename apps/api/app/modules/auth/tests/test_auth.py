"""Tests for auth, PAT, and org management endpoints."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import cast

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select

import app.modules.auth.port.http.deps as auth_deps
import app.modules.auth.port.http.router as auth_router
from app.core.config import load_config
from app.main import app
from app.shared.api.schemas import User
from app.shared.db.models import UserORM


def test_oauth_callback_url_uses_public_frontend_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_router,
        "load_config",
        lambda: SimpleNamespace(
            app=SimpleNamespace(frontend_url="https://platform.example/app/")
        ),
    )

    assert (
        auth_router._oauth_callback_url("github")
        == "https://platform.example/api/v1/auth/oauth/github/callback"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str, password: str, name: str) -> Response:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    return resp


def _login(client: TestClient, email: str, password: str) -> Response:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _promote_superadmin(email: str) -> None:
    """Directly promote a user to superadmin via DB."""
    from app.modules.auth.port.http.deps import _get_session_factory
    sf = _get_session_factory()
    async with sf() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.is_superadmin = True
            await session.commit()


def _make_superadmin(client: TestClient, email: str, password: str, name: str) -> str:
    """Register + promote to superadmin, return token."""
    _register(client, email, password, name)
    import asyncio
    asyncio.run(_promote_superadmin(email))
    resp = _login(client, email, password)
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Register tests
# ---------------------------------------------------------------------------


def test_register_success() -> None:
    with TestClient(app) as c:
        resp = _register(c, "reg_success@test.com", "pass123", "Test User")
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "reg_success@test.com"
        assert body["name"] == "Test User"
        assert "id" in body
        assert body["is_superadmin"] is False
        assert "created_at" in body


def test_register_duplicate_email_returns_409() -> None:
    with TestClient(app) as c:
        _register(c, "dup@test.com", "pass123", "User A").raise_for_status()
        resp = _register(c, "dup@test.com", "pass456", "User B")
        assert resp.status_code == 409
        assert "already" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


def test_login_success_returns_token() -> None:
    with TestClient(app) as c:
        _register(c, "login_ok@test.com", "mypass", "Login User").raise_for_status()
        resp = _login(c, "login_ok@test.com", "mypass")
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["user"]["email"] == "login_ok@test.com"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


class _FailingRedis:
    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        raise RuntimeError("redis unavailable")


def _request_with_redis(redis_client: object) -> Request:
    publisher = SimpleNamespace(_redis=redis_client)
    shared = SimpleNamespace(redis_event_publisher=publisher)
    app_context = SimpleNamespace(shared=shared)
    state = SimpleNamespace(app_context=app_context)
    return cast(Request, SimpleNamespace(app=SimpleNamespace(state=state)))


def test_dev_profile_requires_authentication(monkeypatch) -> None:
    monkeypatch.setenv("APP_CONFIG_PROFILE", "dev")
    load_config.cache_clear()
    protected_app = FastAPI()

    @protected_app.get("/protected")
    async def protected_route(
        _user: User = Depends(auth_deps.get_current_user),
    ) -> dict[str, bool]:
        return {"authenticated": True}

    try:
        with TestClient(protected_app, raise_server_exceptions=False) as client:
            response = client.get("/protected")
    finally:
        load_config.cache_clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_jwt_decode_daily_login_event_is_deduped_by_redis(caplog) -> None:
    from app.modules.auth.port.http.deps import _record_daily_jwt_login_seen

    caplog.set_level(logging.INFO, logger="app.modules.auth.port.http.deps")
    request = _request_with_redis(_FakeRedis())

    asyncio.run(_record_daily_jwt_login_seen(request, "user-123"))
    asyncio.run(_record_daily_jwt_login_seen(request, "user-123"))

    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.user_login"
    ]
    assert len(records) == 1
    assert records[0].user_id == "user-123"
    assert records[0].auth_method == "jwt"
    assert records[0].login_date_utc


def test_jwt_decode_daily_login_event_ignores_redis_failure() -> None:
    from app.modules.auth.port.http.deps import _record_daily_jwt_login_seen

    request = _request_with_redis(_FailingRedis())

    asyncio.run(_record_daily_jwt_login_seen(request, "user-123"))


def test_login_wrong_password_returns_401() -> None:
    with TestClient(app) as c:
        _register(c, "wrong_pw@test.com", "correct", "User").raise_for_status()
        resp = _login(c, "wrong_pw@test.com", "wrong")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me tests
# ---------------------------------------------------------------------------


def test_auth_me_returns_user_with_orgs() -> None:
    with TestClient(app) as c:
        _register(c, "me_test@test.com", "pass123", "Me User").raise_for_status()
        token = _login(c, "me_test@test.com", "pass123").json()["access_token"]
        resp = c.get("/api/v1/auth/me", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me_test@test.com"
        assert "organizations" in body
        assert isinstance(body["organizations"], list)


def test_auth_me_no_token_returns_401() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PAT tests
# ---------------------------------------------------------------------------


def test_pat_create_and_list() -> None:
    with TestClient(app) as c:
        _register(c, "pat_user@test.com", "pass123", "Pat User").raise_for_status()
        token = _login(c, "pat_user@test.com", "pass123").json()["access_token"]

        # Create PAT
        resp = c.post("/api/v1/auth/tokens", json={"name": "my-token"}, headers=_auth(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "my-token"
        assert "token" in body
        assert body["token"].startswith("ftp_")
        token_id = body["id"]

        # List PATs — should contain ours
        resp = c.get("/api/v1/auth/tokens", headers=_auth(token))
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()]
        assert token_id in ids
        # No token_hash returned
        for t in resp.json():
            assert "token_hash" not in t
            assert "token_prefix" in t


def test_pat_delete() -> None:
    with TestClient(app) as c:
        _register(c, "pat_del@test.com", "pass123", "Del User").raise_for_status()
        token = _login(c, "pat_del@test.com", "pass123").json()["access_token"]

        # Create
        resp = c.post("/api/v1/auth/tokens", json={"name": "del-me"}, headers=_auth(token))
        token_id = resp.json()["id"]

        # Delete
        resp = c.delete(f"/api/v1/auth/tokens/{token_id}", headers=_auth(token))
        assert resp.status_code == 204

        # Gone from list
        listed = c.get("/api/v1/auth/tokens", headers=_auth(token)).json()
        assert all(t["id"] != token_id for t in listed)

        # Delete again → 404
        resp = c.delete(f"/api/v1/auth/tokens/{token_id}", headers=_auth(token))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Org management tests
# ---------------------------------------------------------------------------


def test_create_org_as_superadmin() -> None:
    with TestClient(app) as c:
        superadmin_token = _make_superadmin(c, "sa_org@test.com", "pass123", "Super Admin")
        resp = c.post(
            "/api/v1/organizations",
            json={"name": "Test Org", "slug": "test-org-sa"},
            headers=_auth(superadmin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Test Org"
        assert body["slug"] == "test-org-sa"
        assert "id" in body


def test_create_org_as_regular_user_returns_403() -> None:
    with TestClient(app) as c:
        _register(c, "reg_org@test.com", "pass123", "Regular User").raise_for_status()
        token = _login(c, "reg_org@test.com", "pass123").json()["access_token"]
        resp = c.post(
            "/api/v1/organizations",
            json={"name": "Should Fail", "slug": "should-fail"},
            headers=_auth(token),
        )
        assert resp.status_code == 403


def test_add_member_to_org() -> None:
    with TestClient(app) as c:
        superadmin_token = _make_superadmin(c, "sa_add@test.com", "pass123", "SA Add")
        # Create org
        org_resp = c.post(
            "/api/v1/organizations",
            json={"name": "Member Org", "slug": "member-org-add"},
            headers=_auth(superadmin_token),
        )
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Register target user
        user_resp = _register(c, "member_add@test.com", "pass123", "New Member")
        user_id = user_resp.json()["id"]

        # Add member
        resp = c.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"user_id": user_id, "role": "member"},
            headers=_auth(superadmin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == user_id
        assert body["role"] == "member"
        assert body["user_email"] == "member_add@test.com"


def test_list_members() -> None:
    with TestClient(app) as c:
        superadmin_token = _make_superadmin(c, "sa_list@test.com", "pass123", "SA List")
        # Create org
        org_resp = c.post(
            "/api/v1/organizations",
            json={"name": "List Org", "slug": "list-org-members"},
            headers=_auth(superadmin_token),
        )
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Register + add another member
        user_resp = _register(c, "list_member@test.com", "pass123", "List Member")
        user_id = user_resp.json()["id"]
        c.post(
            f"/api/v1/organizations/{org_id}/members",
            json={"user_id": user_id, "role": "member"},
            headers=_auth(superadmin_token),
        ).raise_for_status()

        # List members
        resp = c.get(f"/api/v1/organizations/{org_id}/members", headers=_auth(superadmin_token))
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 2  # superadmin + member
        user_ids = [m["user_id"] for m in members]
        assert user_id in user_ids
