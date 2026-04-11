from __future__ import annotations

import asyncio
import time
from pathlib import Path
from uuid import uuid4

from dependency_injector import providers
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]

import os
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_CONFIG_PROFILE", "test")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./bench-sample-upload-{uuid4().hex}.db"

from app.api.deps import get_current_org, get_current_user
from app.core.config import load_config
from app.db.base import Base
from app.db.session import create_engine
from app.domain.models import Organization, User
from app.main import app, container


def reset_database() -> None:
    load_config.cache_clear()
    container.reset_singletons()

    cfg = load_config()
    engine = create_engine(str(cfg.db.url))

    async def _reset() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_reset())


def install_overrides() -> None:
    user = User(
        id="bench-user",
        email="bench@example.com",
        name="Bench User",
        is_superadmin=True,
        is_active=True,
    )
    org = Organization(
        id="bench-org",
        name="Bench Org",
        slug="bench-org",
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_org] = lambda: org

    mock_ls = MagicMock()
    mock_ls.create_project = AsyncMock(return_value={"id": 1, "title": "bench-project"})
    mock_ls.update_project = AsyncMock(return_value={"id": 1, "title": "bench-project"})
    mock_ls.create_task = AsyncMock(side_effect=lambda project_id, payload: {"id": int(time.time_ns() % 1_000_000_000)})
    mock_ls.create_annotation = AsyncMock(return_value={"id": 0, "task": 0, "result": []})
    mock_ls.list_tasks = AsyncMock(return_value=([], 0))
    mock_ls.list_annotations = AsyncMock(return_value=[])
    mock_ls.export_project = AsyncMock(return_value=[])
    container.label_studio_client.override(providers.Object(mock_ls))


def clear_overrides() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_org, None)
    container.label_studio_client.reset_override()
    container.reset_singletons()
    load_config.cache_clear()


def benchmark(sample_count: int = 5000) -> None:
    reset_database()
    install_overrides()

    started = time.perf_counter()
    with TestClient(app) as client:
        dataset_resp = client.post(
            "/api/v1/datasets",
            json={
                "name": "bench-dataset",
                "task_spec": {"task_type": "classification", "label_space": ["cat", "dog"]},
            },
        )
        dataset_resp.raise_for_status()
        dataset_id = dataset_resp.json()["id"]

        create_started = time.perf_counter()
        for idx in range(sample_count):
            response = client.post(
                f"/api/v1/datasets/{dataset_id}/samples",
                json={
                    "image_uris": [f"memory://samples/{idx}.jpg"],
                    "metadata": {"source": "bench", "index": idx},
                },
            )
            response.raise_for_status()
        create_elapsed = time.perf_counter() - create_started

    total_elapsed = time.perf_counter() - started
    clear_overrides()

    rate = sample_count / create_elapsed if create_elapsed > 0 else 0.0
    projected_seconds = 100_000 / rate if rate > 0 else float("inf")

    print(f"samples_created={sample_count}")
    print(f"create_elapsed_seconds={create_elapsed:.3f}")
    print(f"total_elapsed_seconds={total_elapsed:.3f}")
    print(f"samples_per_second={rate:.2f}")
    print(f"projected_100k_seconds={projected_seconds:.2f}")
    print(f"projected_100k_minutes={projected_seconds / 60.0:.2f}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark dataset sample creation throughput")
    parser.add_argument("--samples", type=int, default=5000, help="Number of samples to create during benchmark")
    args = parser.parse_args()
    benchmark(sample_count=args.samples)
