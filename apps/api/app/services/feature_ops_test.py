from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from app.domain.models import Sample
from app.services.feature_ops import FeatureOpsService


@pytest.mark.asyncio
async def test_extract_features_via_worker_persists_only_successful_embeddings() -> None:
    repository = AsyncMock()
    repository.get_sample_feature.return_value = None
    inference_worker = AsyncMock()
    inference_worker.embed_batch.return_value = [
        {"sample_id": "sample-1", "embedding": [0.1, 0.2, 0.3]},
        {"sample_id": "sample-2", "error": "decode failed"},
    ]
    service = FeatureOpsService(repository=repository, inference_worker=inference_worker)
    samples = [
        Sample(id="sample-1", dataset_id="dataset-1", image_uris=["data:image/png;base64,AA=="]),
        Sample(id="sample-2", dataset_id="dataset-1", image_uris=["data:image/png;base64,AA=="]),
    ]

    result = await service.extract_features_via_worker(
        samples=samples,
        embed_model="clip-test",
        force=False,
        storage=None,
    )

    assert result == {
        "count": 2,
        "computed": 1,
        "skipped": 1,
        "embedding_model": "clip-test",
        "status": "completed",
    }
    inference_worker.embed_batch.assert_awaited_once()
    repository.upsert_sample_feature.assert_awaited_once_with("sample-1", [0.1, 0.2, 0.3], "clip-test")


@pytest.mark.asyncio
async def test_extract_features_via_worker_returns_completed_when_every_sample_is_pre_filtered() -> None:
    repository = AsyncMock()
    repository.get_sample_feature.return_value = SimpleNamespace(embed_model="clip-test")
    inference_worker = AsyncMock()
    service = FeatureOpsService(repository=repository, inference_worker=inference_worker)
    samples = [
        Sample(id="sample-1", dataset_id="dataset-1", image_uris=["data:image/png;base64,AA=="]),
        Sample(id="sample-2", dataset_id="dataset-1", image_uris=[]),
    ]

    result = await service.extract_features_via_worker(
        samples=samples,
        embed_model="clip-test",
        force=False,
        storage=None,
    )

    assert result == {
        "count": 2,
        "computed": 0,
        "skipped": 2,
        "embedding_model": "clip-test",
        "status": "completed",
    }
    inference_worker.embed_batch.assert_not_called()


@pytest.mark.asyncio
async def test_extract_features_via_worker_raises_when_worker_missing_for_selected_samples() -> None:
    repository = AsyncMock()
    repository.get_sample_feature.return_value = None
    service = FeatureOpsService(repository=repository, inference_worker=None)
    samples = [Sample(id="sample-1", dataset_id="dataset-1", image_uris=["data:image/png;base64,AA=="])]

    with pytest.raises(ValueError, match="Inference worker is not configured"):
        await service.extract_features_via_worker(
            samples=samples,
            embed_model="clip-test",
            force=False,
            storage=None,
        )
