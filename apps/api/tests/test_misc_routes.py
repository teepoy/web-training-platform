"""Route-level tests for miscellaneous endpoints.

Covers:
- GET    /organizations
- DELETE /organizations/{org_id}/members/{user_id}
- POST   /task-tracker/tasks/{task_id}/cancel
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

def test_list_organizations() -> None:
    """The mock user is superadmin, so list_all_organizations is called."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/organizations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_remove_org_member_org_not_found() -> None:
    with TestClient(app) as c:
        resp = c.delete("/api/v1/organizations/nonexistent/members/some-user")
        assert resp.status_code == 404


def test_remove_org_member() -> None:
    """Create an org, register a real user, add them as member, then remove."""
    with TestClient(app) as c:
        # Register a real user in the DB
        reg = c.post("/api/v1/auth/register", json={
            "email": "member@test.com",
            "password": "pass1234",
            "name": "Member",
        })
        assert reg.status_code in (200, 201)
        member_user_id = reg.json()["id"]

        # Create org (mock user is superadmin)
        org_resp = c.post("/api/v1/organizations", json={"name": "test-org"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Add the registered user as member
        add_resp = c.post(f"/api/v1/organizations/{org_id}/members", json={
            "user_id": member_user_id,
            "role": "member",
        })
        assert add_resp.status_code in (200, 201)

        # Remove member
        del_resp = c.delete(f"/api/v1/organizations/{org_id}/members/{member_user_id}")
        assert del_resp.status_code == 204


def test_remove_org_member_not_found() -> None:
    with TestClient(app) as c:
        org_resp = c.post("/api/v1/organizations", json={"name": "test-org-2"})
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        resp = c.delete(f"/api/v1/organizations/{org_id}/members/nonexistent-user")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task tracker cancel
# ---------------------------------------------------------------------------

def test_cancel_task_tracker_not_found() -> None:
    with TestClient(app) as c:
        resp = c.post("/api/v1/task-tracker/tasks/nonexistent/cancel")
        assert resp.status_code == 404
