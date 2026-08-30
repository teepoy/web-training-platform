from __future__ import annotations

from datetime import datetime, timedelta
import os

import httpx


def publish_dev_showcase(
    *,
    inspection_time: str,
    total_defects: int,
    imaged_defects: int,
    images_per_defect: int,
    gallery_defects: int,
    gallery_imaged_defects: int,
    defects_per_archive: int,
    append_batch_size: int,
) -> None:
    base_url = _required_environment("UPSTREAM_MOCK_URL").rstrip("/")
    token = _required_environment("UPSTREAM_MOCK_TOKEN")
    timeout_seconds = float(_required_environment("UPSTREAM_MOCK_TIMEOUT_SECONDS"))
    if timeout_seconds <= 0:
        raise ValueError("UPSTREAM_MOCK_TIMEOUT_SECONDS must be positive")
    source_time = datetime.fromisoformat(inspection_time.replace("Z", "+00:00"))
    if source_time.tzinfo is None or source_time.utcoffset() is None:
        raise ValueError("--sc-inspection-time must include a timezone offset")
    response = httpx.post(
        f"{base_url}/api/v1/scenarios/dev-showcase",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
        json={
            "inspection_time": source_time.isoformat(),
            "published_at": (source_time + timedelta(minutes=5)).isoformat(),
            "total_defects": total_defects,
            "imaged_defects": imaged_defects,
            "images_per_defect": images_per_defect,
            "gallery_defects": gallery_defects,
            "gallery_imaged_defects": gallery_imaged_defects,
            "defects_per_archive": defects_per_archive,
            "append_batch_size": append_batch_size,
        },
    )
    response.raise_for_status()
    inspections = response.json()["inspections"]
    created = sum(not item["reused"] for item in inspections)
    reused = len(inspections) - created
    print(
        "  Upstream mock showcase published through HTTP: "
        f"created={created}, reused={reused}"
    )


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
