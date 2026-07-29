"""Tests for the embedding client — gRPC server is fully mocked (never called)."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEFAULT_ORG_ID

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}

_ONE_PX_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

FAKE_EMBEDDING: list[float] = [0.1] * 512


async def _fake_embed_image(
    image_bytes: bytes, model_name: str = "openai/clip-vit-base-patch32"
) -> list[float]:
    return FAKE_EMBEDDING


def _create_dataset_and_sample(c: TestClient, with_image: bool = False) -> tuple[str, str]:
    ds = c.post(
        "/api/v1/datasets",
        json={"name": "embed-test-ds", "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    image_uris = [_ONE_PX_PNG] if with_image else []
    sample = c.post(
        f"/api/v1/datasets/{dataset_id}/samples",
        json={"image_uris": image_uris},
    )
    assert sample.status_code == 200
    return dataset_id, sample.json()["id"]


def test_upsert_and_get_sample_feature() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c, with_image=False)

        async def _run() -> None:
            storage = await app.state.app_context.storage.dataset_storage_factory.open(
                dataset_id,
                org_id=DEFAULT_ORG_ID,
            )
            await storage.upsert_sample_feature(sample_id, FAKE_EMBEDDING, "test-model")

            got = await storage.get_sample_feature(sample_id)
            assert got is not None
            assert got.sample_id == sample_id
            assert got.embed_model == "test-model"
            assert len(got.embedding) == 512

        asyncio.run(_run())


def test_get_sample_feature_returns_none_for_missing() -> None:
    with TestClient(app) as c:
        dataset_id, _ = _create_dataset_and_sample(c, with_image=False)

        async def _run() -> None:
            storage = await app.state.app_context.storage.dataset_storage_factory.open(
                dataset_id,
                org_id=DEFAULT_ORG_ID,
            )
            result = await storage.get_sample_feature("does-not-exist-at-all")
            assert result is None

        asyncio.run(_run())


def test_upsert_sample_feature_idempotent() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c, with_image=False)

        async def _run() -> None:
            storage = await app.state.app_context.storage.dataset_storage_factory.open(
                dataset_id,
                org_id=DEFAULT_ORG_ID,
            )

            first = [0.1] * 512
            second = [0.9] * 512

            await storage.upsert_sample_feature(sample_id, first, "model-v1")
            await storage.upsert_sample_feature(sample_id, second, "model-v2")

            got = await storage.get_sample_feature(sample_id)
            assert got is not None
            assert got.embed_model == "model-v2"
            assert got.embedding[0] == 0.9

        asyncio.run(_run())
