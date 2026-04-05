from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("APP_CONFIG_PROFILE", "local-smoke")


def _register_user(client, email: str, password: str, name: str) -> dict:
    """Call POST /api/v1/auth/register, return user dict"""
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})
    resp.raise_for_status()
    return resp.json()


def _login_user(client, email: str, password: str) -> str:
    """Call POST /api/v1/auth/login, return access_token string"""
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    """Return Authorization Bearer header dict"""
    return {"Authorization": f"Bearer {token}"}


def _org_headers(org_id: str, token: str) -> dict:
    """Return auth + org context headers"""
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _create_org(client, name: str, admin_token: str) -> dict:
    """Call POST /api/v1/organizations, return org dict. Stub — endpoint added in T12."""
    resp = client.post("/api/v1/organizations", json={"name": name}, headers=_auth_headers(admin_token))
    resp.raise_for_status()
    return resp.json()


def _add_member(client, org_id: str, user_id: str, role: str, admin_token: str) -> dict:
    """Add user to org. Stub — endpoint added in T12."""
    resp = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": user_id, "role": role},
        headers=_auth_headers(admin_token),
    )
    resp.raise_for_status()
    return resp.json()
