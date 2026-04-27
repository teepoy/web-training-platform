from __future__ import annotations

import subprocess
import time

import httpx

DEFAULT_SEED_EMAIL = "seed@example.com"
DEFAULT_SEED_PASSWORD = "seed1234"
DEFAULT_SEED_NAME = "Seed Admin"
DEFAULT_ORG_NAME = "Default Org"
DEFAULT_ORG_SLUG = "default-org"
DEFAULT_COMPOSE_FILE = "infra/compose/docker-compose.yaml"


def api_request(
    client: httpx.Client, method: str, path: str, **kwargs
) -> httpx.Response:
    return getattr(client, method)(path, **kwargs)


def promote_superadmin(compose_file: str, email: str, password: str, name: str) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "api",
        "uv",
        "run",
        "python",
        "-m",
        "app.cli",
        "create-superadmin",
        f"--email={email}",
        f"--password={password}",
        f"--name={name}",
    ]
    print(f"  Promoting {email} to superadmin via docker exec ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"  WARNING: promote failed (rc={result.returncode}): {result.stderr.strip()}"
        )
        print(
            "  If running locally, use: make create-superadmin "
            f"EMAIL={email} PASSWORD={password} NAME='{name}'"
        )
    else:
        print(f"  {result.stdout.strip()}")


def wait_for_api_ready(client: httpx.Client, timeout_seconds: float = 120.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = client.get("/health")
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(f"API not ready after {timeout_seconds:.0f}s: {last_error}")


def register_seed_user(
    client: httpx.Client, email: str, password: str, name: str
) -> httpx.Response:
    return api_request(
        client,
        "post",
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def login_seed_user(client: httpx.Client, email: str, password: str) -> httpx.Response:
    return api_request(
        client,
        "post",
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def resolve_or_create_org(
    client: httpx.Client, org_name: str, org_slug: str
) -> str | None:
    response = api_request(client, "get", "/api/v1/organizations")
    orgs = response.json() if response.status_code == 200 else []
    org_id: str | None = None
    for org in orgs:
        if org.get("slug") == org_slug or org.get("name") == org_name:
            org_id = org["id"]
            break

    if org_id:
        return org_id

    response = api_request(
        client,
        "post",
        "/api/v1/organizations",
        json={"name": org_name, "slug": org_slug},
    )
    if response.status_code in (200, 201):
        return response.json()["id"]

    if orgs:
        return orgs[0]["id"]
    return None
