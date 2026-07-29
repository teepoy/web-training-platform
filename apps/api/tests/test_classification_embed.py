"""Regression tests for the embed_fn callback and 8×8 gray fallback.

These tests verify:
1.  ``_image_embedding_from_bytes`` with a mock ``embed_fn`` correctly pads,
    truncates, and normalises returned vectors.
2.  The fallback path (no ``embed_fn`` → 8×8 grayscale) still produces 64‑dim
    vectors (backward compatible).
3.  ``ClassificationTrainer`` passes its ``embed_fn`` through during training.
4.  ``ClassificationPredictor`` passes its ``embed_fn`` through during
    prediction.
5.  ``DetectionTrainer`` still works without ``embed_fn`` (backward compat).
"""

from __future__ import annotations

import base64
import json
import math
from io import BytesIO

import pytest
from PIL import Image

from app.runtime_compat.ml.demo.classification._utils import (
    _image_embedding_from_bytes,
)
from app.runtime_compat.ml.demo.classification.predictor import (
    ClassificationPredictor,
)
from app.runtime_compat.ml.demo.classification.trainer import ClassificationTrainer
from app.runtime_compat.ml.demo.detection.predictor import DetectionPredictor
from app.runtime_compat.ml.demo.detection.trainer import DetectionTrainer
from app.runtime_compat.ml.demo.domain import (
    DatasetRef,
    ModelRef,
    PredictContext,
    TrainContext,
)

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _png_bytes(size: tuple[int, int] = (16, 16), color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    """Return a small PNG as raw bytes."""
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _data_uri(image_bytes: bytes) -> str:
    """Wrap raw PNG bytes in a ``data:`` URI."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class _MockArtifactStorage:
    """In-memory artifact store — no external dependencies."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._store[object_name] = data
        return f"memory://{object_name}"

    async def get_bytes(self, uri: str) -> bytes:
        key = uri.split("://", 1)[1]
        return self._store[key]

    async def delete(self, uri: str) -> None:
        key = uri.split("://", 1)[1]
        self._store.pop(key, None)

    async def list_prefix(self, prefix: str) -> list[str]:
        return [f"memory://{key}" for key in self._store if key.startswith(prefix)]


# ═══════════════════════════════════════════════════════════════════════
# 1.  _image_embedding_from_bytes with embed_fn
# ═══════════════════════════════════════════════════════════════════════


class TestImageEmbeddingWithEmbedFn:
    """Direct unit tests on the ``embed_fn`` path."""

    def test_embed_fn_512dim_full(self) -> None:
        """embed_fn returns 512‑dim vector, ``dim=512`` → 512‑dim normalised."""

        def embed_fn(_b: bytes) -> list[float]:
            return [0.1] * 512

        vec = _image_embedding_from_bytes(b"test", dim=512, embed_fn=embed_fn)
        assert len(vec) == 512
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_embed_fn_truncate_to_64(self) -> None:
        """embed_fn returns 512‑dim vector, default ``dim=64`` → truncated + normalised."""

        def embed_fn(_b: bytes) -> list[float]:
            return [0.1] * 512

        vec = _image_embedding_from_bytes(b"test", embed_fn=embed_fn)
        assert len(vec) == 64
        # First 64 values of [0.1]*512, normalised
        raw = [0.1] * 64
        n = math.sqrt(sum(x * x for x in raw))
        expected = [x / n for x in raw]
        for a, b in zip(vec, expected):
            assert abs(a - b) < 1e-6, f"expected {b}, got {a}"

    def test_embed_fn_pad_to_64(self) -> None:
        """embed_fn returns 8‑dim vector → padded to 64‑dim, then normalised."""

        def embed_fn(_b: bytes) -> list[float]:
            return [1.0] * 8

        vec = _image_embedding_from_bytes(b"test", embed_fn=embed_fn)
        assert len(vec) == 64
        raw = [1.0] * 8 + [0.0] * 56
        n = math.sqrt(sum(x * x for x in raw))
        expected = [x / n for x in raw]
        for a, b in zip(vec, expected):
            assert abs(a - b) < 1e-6, f"expected {b}, got {a}"


# ═══════════════════════════════════════════════════════════════════════
# 2.  _image_embedding_from_bytes fallback (8×8 gray)
# ═══════════════════════════════════════════════════════════════════════


class TestImageEmbeddingFallback:
    """Verify the 8×8 grayscale fallback still works without ``embed_fn``."""

    def test_fallback_returns_64dim_normalised(self) -> None:
        """A non‑trivial image yields a normalised 64‑dim vector."""
        img_bytes = _png_bytes(color=(64, 128, 192))
        vec = _image_embedding_from_bytes(img_bytes)
        assert len(vec) == 64
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_fallback_black_image(self) -> None:
        """A black image produces all‑zero embedding without NaN."""
        img_bytes = _png_bytes(color=(0, 0, 0))
        vec = _image_embedding_from_bytes(img_bytes)
        assert len(vec) == 64
        assert all(math.isfinite(v) for v in vec)
        # All zeros → no normalisation applied
        assert all(v == 0.0 for v in vec)


# ═══════════════════════════════════════════════════════════════════════
# 3.  ClassificationTrainer with embed_fn
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_classification_trainer_with_embed_fn() -> None:
    """Trainer with mock ``embed_fn`` yields 64‑dim prototype vectors."""
    storage = _MockArtifactStorage()
    cat_bytes = _png_bytes(color=(200, 100, 50))
    dog_bytes = _png_bytes(color=(50, 100, 200))

    def mock_embed_fn(b: bytes) -> list[float]:
        if b == cat_bytes:
            return [1.0] + [0.0] * 511
        return [0.0] * 512  # dog gets a zero vector

    trainer = ClassificationTrainer(artifact_storage=storage, embed_fn=mock_embed_fn)
    ctx = TrainContext(
        job_id="test-cls-embed-3",
        model_ref=ModelRef(architecture="test", framework="pytorch"),
        dataset_ref=DatasetRef(
            dataset_id="test-ds",
            label_space=["cat", "dog"],
            metadata={
                "records": [
                    {"label": "cat", "image_uri": _data_uri(cat_bytes)},
                    {"label": "dog", "image_uri": _data_uri(dog_bytes)},
                ]
            },
        ),
    )

    result = await trainer.train(ctx)

    assert result.model_uri is not None
    assert result.metrics["trained_samples"] == 2

    model_bytes = await storage.get_bytes(result.model_uri)
    model = json.loads(model_bytes.decode("utf-8"))
    prototypes = model["label_prototypes"]

    # Both prototypes should be 64-dim (truncated from embed_fn's 512-dim)
    assert len(prototypes["cat"]) == 64
    assert len(prototypes["dog"]) == 64


# ═══════════════════════════════════════════════════════════════════════
# 4.  ClassificationPredictor with embed_fn
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_classification_predictor_with_embed_fn() -> None:
    """Predictor with mock ``embed_fn`` classifies correctly."""
    storage = _MockArtifactStorage()
    cat_bytes = _png_bytes(color=(200, 100, 50))
    dog_bytes = _png_bytes(color=(50, 100, 200))

    def mock_embed_fn(b: bytes) -> list[float]:
        if b == cat_bytes:
            return [1.0] + [0.0] * 511  # cat → unit vector along dim 0
        return [0.0] * 512  # everything else → zero vector

    # ── train ────────────────────────────────────────────────────────
    trainer = ClassificationTrainer(artifact_storage=storage, embed_fn=mock_embed_fn)
    train_ctx = TrainContext(
        job_id="test-cls-pred-4",
        model_ref=ModelRef(architecture="test", framework="pytorch"),
        dataset_ref=DatasetRef(
            dataset_id="test-ds",
            label_space=["cat", "dog"],
            metadata={
                "records": [
                    {"label": "cat", "image_uri": _data_uri(cat_bytes)},
                    {"label": "dog", "image_uri": _data_uri(dog_bytes)},
                ]
            },
        ),
    )
    train_result = await trainer.train(train_ctx)

    model_bytes = await storage.get_bytes(train_result.model_uri)
    model = json.loads(model_bytes.decode("utf-8"))
    prototypes = model["label_prototypes"]

    # Sanity: cat prototype should be non-zero, dog prototype should be zero
    assert any(v != 0.0 for v in prototypes["cat"])
    assert all(v == 0.0 for v in prototypes["dog"])

    # ── predict ──────────────────────────────────────────────────────
    predictor = ClassificationPredictor(
        artifact_storage=storage,
        embed_fn=mock_embed_fn,
    )
    model_ref = ModelRef(uri=train_result.model_uri)
    await predictor.load_model(model_ref)

    pred_ctx = PredictContext(
        job_id="test-pred-4",
        dataset_ref=DatasetRef(
            dataset_id="test-ds",
            label_space=["cat", "dog"],
        ),
    )

    result = await predictor.predict_single(
        pred_ctx,
        {"sample_id": "s1", "image_bytes": cat_bytes},
    )

    assert result.sample_id == "s1"
    assert result.label == "cat", f"expected 'cat', got '{result.label}'"
    assert result.confidence is not None and result.confidence > 0.5
    assert "cat" in result.scores
    assert "dog" in result.scores
    assert result.scores["cat"] > result.scores["dog"]


# ═══════════════════════════════════════════════════════════════════════
# 5.  DetectionTrainer backward compat (no embed_fn → 8×8 gray)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_detection_trainer_backward_compat() -> None:
    """DetectionTrainer uses the default 8×8 gray embedding."""
    storage = _MockArtifactStorage()
    img_bytes = _png_bytes()

    trainer = DetectionTrainer(artifact_storage=storage)
    ctx = TrainContext(
        job_id="test-det-bc-5",
        model_ref=ModelRef(architecture="test", framework="pytorch"),
        dataset_ref=DatasetRef(
            dataset_id="test-ds",
            label_space=["car", "person"],
            metadata={
                "records": [
                    {"label": "car", "image_uri": _data_uri(img_bytes)},
                    {"label": "person", "image_uri": _data_uri(img_bytes)},
                ]
            },
        ),
    )

    result = await trainer.train(ctx)

    assert result.model_uri is not None
    assert result.metrics["trained_samples"] == 2

    model_bytes = await storage.get_bytes(result.model_uri)
    model = json.loads(model_bytes.decode("utf-8"))
    prototypes = model["label_prototypes"]

    for label in ("car", "person"):
        vec = prototypes[label]
        assert len(vec) == 64, f"{label} prototype expected 64 dims, got {len(vec)}"
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6, f"{label} prototype should be normalised"


@pytest.mark.asyncio
@pytest.mark.parametrize("trainer_cls", [ClassificationTrainer, DetectionTrainer])
async def test_trainer_rejects_dataset_without_readable_labeled_images(
    trainer_cls,
) -> None:
    storage = _MockArtifactStorage()
    trainer = trainer_cls(artifact_storage=storage)
    ctx = TrainContext(
        job_id="empty-training-data",
        model_ref=ModelRef(architecture="test", framework="pytorch"),
        dataset_ref=DatasetRef(
            dataset_id="test-ds",
            label_space=["cat", "dog"],
            metadata={"records": []},
        ),
    )

    with pytest.raises(
        ValueError,
        match="no labeled samples with readable images",
    ):
        await trainer.train(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("predictor_cls", "message"),
    [
        (ClassificationPredictor, "valid classification prototype JSON"),
        (DetectionPredictor, "valid detection prototype JSON"),
    ],
)
async def test_predictor_rejects_corrupt_model_artifact(
    predictor_cls,
    message: str,
) -> None:
    storage = _MockArtifactStorage()
    uri = await storage.put_bytes("models/corrupt.json", b"not-json")
    predictor = predictor_cls(artifact_storage=storage)

    with pytest.raises(ValueError, match=message):
        await predictor.load_model(
            ModelRef(
                uri=uri,
                metadata={"label_space": ["cat", "dog"]},
            )
        )
