"""Test BatchPredictionService — latest prediction per sample batch lookup."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.prediction.app.services.batch_lookup import BatchPredictionService
from app.modules.prediction.port.http.schemas import PredictionResultResponse


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
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.sample_id = sample_id
    row.predicted_label = predicted_label
    row.confidence = confidence
    row.model_id = model_id
    row.target = target
    row.model_version = model_version
    row.job_id = job_id
    row.created_at = created_at
    row.error = error
    return row


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

    mock_rows = [row_s1_new, row_s2]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_rows

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.session_factory.return_value = mock_session_cm

    svc = BatchPredictionService(mock_repo)
    results = await svc.get_latest_predictions("ds_test")

    assert len(results) == 2
    assert all(isinstance(r, PredictionResultResponse) for r in results)
    assert results[0].sample_id == "s1"
    assert results[0].predicted_label == "Scratch"
    assert results[0].confidence == 0.95
    assert results[1].sample_id == "s2"
    assert results[1].predicted_label == "Clean"
    assert results[1].confidence == 0.80


@pytest.mark.asyncio
async def test_get_latest_predictions_empty_dataset():
    """Empty dataset returns empty list, no error."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.session_factory.return_value = mock_session_cm

    svc = BatchPredictionService(mock_repo)
    results = await svc.get_latest_predictions("ds_empty")

    assert results == []


@pytest.mark.asyncio
async def test_get_latest_predictions_deduplicates_same_sample():
    """When the subquery+join returns duplicates, only first per sample kept."""
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    row_s1_a = _make_prediction_row("p1", "s1", "A", confidence=0.7, created_at=now)
    row_s1_b = _make_prediction_row("p2", "s1", "A", confidence=0.7, created_at=now)
    row_s2 = _make_prediction_row("p3", "s2", "B", confidence=0.9, created_at=now)

    # Simulate duplicate: both rows for s1 may appear if created_at ties
    mock_rows = [row_s1_a, row_s1_b, row_s2]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_rows

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session

    mock_repo = MagicMock()
    mock_repo.session_factory.return_value = mock_session_cm

    svc = BatchPredictionService(mock_repo)
    results = await svc.get_latest_predictions("ds_test")

    # Dedup: first s1 kept, second s1 skipped
    assert len(results) == 2
    sample_ids = [r.sample_id for r in results]
    assert sample_ids == ["s1", "s2"]
