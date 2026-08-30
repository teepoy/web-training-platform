from __future__ import annotations

import base64
import io
import os
import time

import httpx

_COLOR_MAP: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
}


def wait_for_api_ready(api_url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{api_url}/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("API health check timed out")


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for live smoke authentication")
    return value


def login_smoke_user(api_url: str) -> str:
    response = httpx.post(
        f"{api_url}/api/v1/auth/login",
        json={
            "email": _required_environment("SMOKE_USER_EMAIL"),
            "password": _required_environment("SMOKE_USER_PASSWORD"),
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def resolve_smoke_org(api_url: str, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(f"{api_url}/api/v1/organizations", headers=headers)
    response.raise_for_status()
    orgs = response.json()
    if not isinstance(orgs, list) or not orgs:
        raise RuntimeError("No organizations available for the explicit smoke user")
    return str(orgs[0]["id"])


def create_smoke_dataset(
    client: httpx.Client,
    api_url: str,
    headers: dict[str, str],
    name: str,
) -> str:
    response = client.post(
        f"{api_url}/api/v1/datasets",
        headers=headers,
        json={
            "name": name,
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": ["red", "blue"],
            },
        },
    )
    response.raise_for_status()
    return str(response.json()["id"])


def smoke_failure(message: str) -> int:
    print(f"Smoke test failed: {message}")
    return 1


def create_synthetic_image(label: str, size: int = 32) -> str:
    from PIL import (
        Image,
    )  # lazy import — only needed by training/prediction smoke scripts

    color = _COLOR_MAP.get(label.lower(), (128, 128, 128))
    image = Image.new("RGB", (size, size), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
