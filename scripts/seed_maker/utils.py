from __future__ import annotations

import time
from typing import Any

import httpx

DEFAULT_COMPOSE_FILE = "infra/compose/docker-compose.yaml"
DEFAULT_SEED_EMAIL = "seed@example.com"
DEFAULT_SEED_PASSWORD = "seed1234"
DEFAULT_SEED_NAME = "Seed Admin"
DEFAULT_ORG_NAME = "Default Org"
DEFAULT_ORG_SLUG = "default-org"


def api_request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    return getattr(client, method)(path, **kwargs)


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


def _find_by_name(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None
