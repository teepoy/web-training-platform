"""Tests for the worker-only ClipPredictor demo.

These tests verify:
1.  The demo is not exposed as a deployed product capability.
2.  The factory accepts an embedding_client kwarg and returns a ClipPredictor.
3.  A mock embedding client drives predict_single correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.registry import get_predictor_by_id
from app.modules.types import catalog
from app.runtime_compat.ml.demo.registrations.clip import (
    ClipPredictor,
    ClipPredictorFactory,
)
from app.runtime_compat.ml.demo.domain import (
    DatasetRef,
    ModelRef,
    PredictContext,
)


# ═══════════════════════════════════════════════════════════════════════
# 1.  Registry resolution
# ═══════════════════════════════════════════════════════════════════════


def test_clip_demo_is_not_exposed_as_runtime_capability() -> None:
    with pytest.raises(KeyError):
        catalog.get_predictor_meta("clip-zero-shot-v1")
    assert get_predictor_by_id("clip-zero-shot-v1") is None


# ═══════════════════════════════════════════════════════════════════════
# 2.  Factory accepts embedding_client kwarg
# ═══════════════════════════════════════════════════════════════════════


def test_clip_predictor_factory_accepts_embedding_client() -> None:
    """Verify the factory creates a ClipPredictor when given embedding_client."""
    mock_client = AsyncMock()
    mock_client.classify_image = AsyncMock(
        return_value=("cat", 0.95, {"cat": 0.95, "dog": 0.05})
    )

    predictor_instance = ClipPredictorFactory(embedding_client=mock_client)

    assert isinstance(predictor_instance, ClipPredictor), (
        "Factory should return a ClipPredictor instance"
    )
    assert hasattr(predictor_instance, "predict_single"), (
        "ClipPredictor should have predict_single method"
    )
    assert hasattr(predictor_instance, "predict_batch"), (
        "ClipPredictor should have predict_batch method"
    )
    assert callable(predictor_instance.predict_single)
    assert callable(predictor_instance.predict_batch)


def test_clip_predictor_factory_raises_without_embedding_client() -> None:
    """Verify the factory raises ValueError when embedding_client is missing."""
    with pytest.raises(ValueError, match="embedding_client is required"):
        ClipPredictorFactory()


# ═══════════════════════════════════════════════════════════════════════
# 3.  Mock prediction with predict_single
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_clip_predictor_mock_prediction() -> None:
    """Verify predict_single returns the expected label and confidence."""
    # ── mock embedding client ──────────────────────────────────────
    mock_client = AsyncMock()
    mock_client.classify_image = AsyncMock(
        return_value=("cat", 0.95, {"cat": 0.95, "dog": 0.05})
    )

    # ── instantiate predictor via factory ──────────────────────────
    predictor_instance = ClipPredictorFactory(embedding_client=mock_client)

    # ── load model with label space ────────────────────────────────
    model_ref = ModelRef(metadata={"label_space": ["cat", "dog"]})
    predictor_instance.load_model(model_ref)

    # ── create context ─────────────────────────────────────────────
    ctx = PredictContext(
        job_id="test-job-1",
        dataset_ref=DatasetRef(
            dataset_id="test-ds-1",
            label_space=[],
        ),
    )

    # ── sample with image bytes ────────────────────────────────────
    sample = {
        "id": "sample-1",
        "image_bytes": b"fake_image_bytes",
    }

    # ── predict ────────────────────────────────────────────────────
    result = await predictor_instance.predict_single(ctx, sample)

    assert result.sample_id == "sample-1"
    assert result.label == "cat"
    assert result.confidence == 0.95
    assert result.scores == {"cat": 0.95, "dog": 0.05}

    # ── verify the mock was called correctly ───────────────────────
    mock_client.classify_image.assert_awaited_once_with(
        b"fake_image_bytes", ["cat", "dog"], "openai/clip-vit-base-patch32"
    )


@pytest.mark.asyncio
async def test_clip_predictor_no_image_bytes() -> None:
    """Verify predict_single returns an error when no image bytes provided."""
    mock_client = AsyncMock()
    predictor_instance = ClipPredictorFactory(embedding_client=mock_client)

    model_ref = ModelRef(metadata={"label_space": ["cat", "dog"]})
    predictor_instance.load_model(model_ref)

    ctx = PredictContext(
        job_id="test-job-2",
        dataset_ref=DatasetRef(dataset_id="test-ds-2"),
    )

    sample = {"id": "sample-2"}

    result = await predictor_instance.predict_single(ctx, sample)

    assert result.sample_id == "sample-2"
    assert result.label == ""
    assert result.confidence == 0.0
    assert result.metadata.get("error") == "no image_bytes in sample"


@pytest.mark.asyncio
async def test_clip_predictor_no_label_space() -> None:
    """Verify predict_single returns an error when no label space."""
    mock_client = AsyncMock()
    predictor_instance = ClipPredictorFactory(embedding_client=mock_client)
    # intentionally NOT calling load_model — label_space stays []

    ctx = PredictContext(
        job_id="test-job-3",
        dataset_ref=DatasetRef(dataset_id="test-ds-3"),
    )

    sample = {"id": "sample-3", "image_bytes": b"ignored"}

    result = await predictor_instance.predict_single(ctx, sample)

    assert result.sample_id == "sample-3"
    assert result.label == ""
    assert result.confidence == 0.0
    assert result.metadata.get("error") == "no label space available"
