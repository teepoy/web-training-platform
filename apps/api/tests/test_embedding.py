"""Tests for the embedding service — CLIP model is fully mocked (never downloaded)."""
from __future__ import annotations

import asyncio
import unittest.mock as mock

from fastapi.testclient import TestClient

from app.main import app
import app.services.embedding as embedding_module

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}

# Minimal 1×1 PNG (valid base64, no real model needed)
_ONE_PX_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

FAKE_EMBEDDING: list[float] = [0.1] * 512


def _mock_embed_sync(self: object, image_bytes: bytes, model_name: str) -> list[float]:  # noqa: ARG001
    return FAKE_EMBEDDING


def _reset_clip_cache() -> None:
    """Ensure no CLIP artifacts leak between tests."""
    embedding_module.EmbeddingService._models = {}
    embedding_module.EmbeddingService._processors = {}


def _create_dataset_and_sample(c: TestClient, with_image: bool = False) -> tuple[str, str]:
    """Create a dataset + sample. Optionally include a data URI image."""
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


# ---------------------------------------------------------------------------
# Test 1: Embed endpoint — success path (200, correct shape + fields)
# ---------------------------------------------------------------------------


def test_embed_sample_success() -> None:
    _reset_clip_cache()
    with mock.patch(
        "app.services.embedding.EmbeddingService._embed_sync",
        _mock_embed_sync,
    ):
        with TestClient(app) as c:
            _, sample_id = _create_dataset_and_sample(c, with_image=True)

            r = c.post(f"/api/v1/samples/{sample_id}/embed")
            assert r.status_code == 200
            body = r.json()
            assert body["sample_id"] == sample_id
            assert body["embedding_dim"] == 512
            assert body["embed_model"] == "openai/clip-vit-base-patch32"
    _reset_clip_cache()


# ---------------------------------------------------------------------------
# Test 2: Embed endpoint — sample has no image → 400
# ---------------------------------------------------------------------------


def test_embed_sample_no_image() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c, with_image=False)

        r = c.post(f"/api/v1/samples/{sample_id}/embed")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Test 3: Embed endpoint — nonexistent sample → 404
# ---------------------------------------------------------------------------


def test_embed_nonexistent_sample() -> None:
    with TestClient(app) as c:
        r = c.post("/api/v1/samples/nonexistent-embed-id/embed")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: upsert_sample_feature then get_sample_feature (repo round-trip)
# ---------------------------------------------------------------------------


def test_upsert_and_get_sample_feature() -> None:
    with TestClient(app) as c:
        # Need a valid sample_id that exists in the DB
        _, sample_id = _create_dataset_and_sample(c, with_image=False)

        async def _run() -> None:
            from app.main import container  # noqa: PLC0415

            repo = container.repository()
            feature = await repo.upsert_sample_feature(sample_id, FAKE_EMBEDDING, "test-model")
            assert feature.sample_id == sample_id
            assert len(feature.embedding) == 512
            assert feature.embed_model == "test-model"

            got = await repo.get_sample_feature(sample_id)
            assert got is not None
            assert got.sample_id == sample_id
            assert got.embed_model == "test-model"
            assert len(got.embedding) == 512

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 5: get_sample_feature returns None for missing sample_id
# ---------------------------------------------------------------------------


def test_get_sample_feature_returns_none_for_missing() -> None:
    with TestClient(app) as c:  # noqa: F841 — need TestClient context to init DB

        async def _run() -> None:
            from app.main import container  # noqa: PLC0415

            repo = container.repository()
            result = await repo.get_sample_feature("does-not-exist-at-all")
            assert result is None

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 6: upsert is idempotent — second upsert updates existing feature
# ---------------------------------------------------------------------------


def test_upsert_sample_feature_idempotent() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c, with_image=False)

        async def _run() -> None:
            from app.main import container  # noqa: PLC0415

            repo = container.repository()

            first = [0.1] * 512
            second = [0.9] * 512

            await repo.upsert_sample_feature(sample_id, first, "model-v1")
            await repo.upsert_sample_feature(sample_id, second, "model-v2")

            got = await repo.get_sample_feature(sample_id)
            assert got is not None
            assert got.embed_model == "model-v2"
            assert got.embedding[0] == 0.9

        asyncio.run(_run())
