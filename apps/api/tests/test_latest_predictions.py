"""Test latest prediction endpoint mapping."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.modules.datasets.port.http.extensions.prediction_router import (
    list_latest_predictions,
)
from app.modules.prediction.port.http.schemas import PredictionResultResponse
from app.shared.api.schemas import (
    Dataset,
    DatasetStorageMode,
    Organization,
    PlatformPrediction,
    TaskSpec,
    User,
)


def _make_prediction_row(
    id: str,
    sample_id: str,
    predicted_label: str,
    confidence: float | None = None,
    model_id: str | None = None,
    target: str | None = None,
    model_version: str | None = None,
    job_id: str | None = None,
    created_at: datetime | None = None,
    error: str | None = None,
) -> PlatformPrediction:
    return PlatformPrediction(
        id=id,
        org_id="org_test",
        dataset_id="ds_test",
        sample_id=sample_id,
        predicted_label=predicted_label,
        confidence=confidence,
        all_scores=None,
        model_id=model_id or "",
        target=target or "image_classification",
        model_version=model_version,
        job_id=job_id,
        created_at=created_at or datetime.now(timezone.utc),
        error=error,
    )


def _make_dataset(storage_mode: DatasetStorageMode = DatasetStorageMode.DB_FULL) -> Dataset:
    return Dataset(
        id="ds_test",
        name="test",
        dataset_type="image_classification",
        task_spec=TaskSpec(task_type="classification", label_space=["A", "B"]),
        storage_mode=storage_mode,
    )


def _make_user() -> User:
    return User(
        id="user_test",
        email="test@test.com",
        name="Test User",
        is_superadmin=True,
        is_active=True,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _make_org() -> Organization:
    return Organization(
        id="org_test",
        name="Test Org",
        slug="test",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _make_storage_factory(predictions: list[PlatformPrediction]) -> AsyncMock:
    storage = AsyncMock()
    storage.list_predictions.return_value = predictions
    factory = AsyncMock()
    factory.open.return_value = storage
    return factory


@pytest.mark.asyncio
async def test_get_latest_predictions_returns_latest_per_sample():
    """Only the most recent prediction per sample is returned."""
    now = datetime(2025, 1, 15, tzinfo=timezone.utc)
    older = datetime(2025, 1, 1, tzinfo=timezone.utc)

    row_s1_new = _make_prediction_row(
        "p3", "s1", "Scratch", confidence=0.95, model_id="m1", target="cls",
        created_at=now,
    )
    row_s2 = _make_prediction_row(
        "p2", "s2", "Clean", confidence=0.80, model_id="m1", target="cls",
        created_at=older,
    )

    storage_factory = _make_storage_factory([row_s1_new, row_s2])
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = _make_dataset()

    results = await list_latest_predictions(
        "ds_test",
        _make_user(),
        _make_org(),
        dataset_reader,
        storage_factory,
        offset=0,
        limit=None,
    )

    assert len(results) == 2
    assert all(isinstance(r, PredictionResultResponse) for r in results)
    assert results[0].sample_id == "s1"
    assert results[0].predicted_label == "Scratch"
    assert results[0].confidence == 0.95
    assert results[1].sample_id == "s2"
    assert results[1].predicted_label == "Clean"
    assert results[1].confidence == 0.80
    storage_factory.open.return_value.list_predictions.assert_awaited_once_with(
        offset=0,
        limit=None,
        latest_per_sample=True,
    )


@pytest.mark.asyncio
async def test_get_latest_predictions_empty_dataset():
    """Empty dataset returns empty list, no error."""
    storage_factory = _make_storage_factory([])
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = _make_dataset(
        DatasetStorageMode.FILE_SHARD_SPARSE
    )

    results = await list_latest_predictions(
        "ds_empty",
        _make_user(),
        _make_org(),
        dataset_reader,
        storage_factory,
        offset=0,
        limit=None,
    )

    assert results == []
    storage_factory.open.return_value.list_predictions.assert_awaited_once_with(
        offset=0,
        limit=None,
        latest_per_sample=True,
    )


@pytest.mark.asyncio
async def test_get_latest_predictions_forwards_pagination():
    """The endpoint delegates latest-per-sample pagination to storage."""
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    row_s1_a = _make_prediction_row("p1", "s1", "A", confidence=0.7, created_at=now)
    row_s2 = _make_prediction_row("p3", "s2", "B", confidence=0.9, created_at=now)

    storage_factory = _make_storage_factory([row_s1_a, row_s2])
    dataset_reader = AsyncMock()
    dataset_reader.get_dataset.return_value = _make_dataset()

    results = await list_latest_predictions(
        "ds_test",
        _make_user(),
        _make_org(),
        dataset_reader,
        storage_factory,
        offset=20,
        limit=10,
    )

    assert len(results) == 2
    sample_ids = [r.sample_id for r in results]
    assert sample_ids == ["s1", "s2"]
    storage_factory.open.return_value.list_predictions.assert_awaited_once_with(
        offset=20,
        limit=10,
        latest_per_sample=True,
    )
