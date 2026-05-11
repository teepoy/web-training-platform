from __future__ import annotations

import base64
import io
import time

import httpx

SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"

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


def login_seed_user(api_url: str) -> str:
    response = httpx.post(
        f"{api_url}/api/v1/auth/login",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def resolve_seed_org(api_url: str, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(f"{api_url}/api/v1/organizations", headers=headers)
    response.raise_for_status()
    orgs = response.json()
    if not isinstance(orgs, list) or not orgs:
        raise RuntimeError("No organizations available for smoke user")
    return str(orgs[0]["id"])


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
