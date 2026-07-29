from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.prediction.app.services.prediction_review import (
    PredictionReviewService,
)
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.domain.review import ReviewAnnotationCommand
from app.modules.datasets.port.local import SampleRow
from app.shared.api.schemas import PlatformPrediction, PredictionReviewAction
from app.shared.infrastructure.label_studio.client import LabelStudioError


def _service(
    repository: PredictionRepository,
    *,
    dataset_exists: bool = True,
    model_exists: bool = True,
) -> PredictionReviewService:
    dataset_reader = SimpleNamespace(
        get_dataset=AsyncMock(
            return_value=SimpleNamespace(id="dataset-1")
            if dataset_exists
            else None
        )
    )
    model_catalog = SimpleNamespace(
        get_model=AsyncMock(
            return_value=SimpleNamespace(id="model-1")
            if model_exists
            else None
        )
    )
    return PredictionReviewService(
        repository=repository,
        config=cast(Any, SimpleNamespace()),
        dataset_storage_factory=cast(Any, SimpleNamespace()),
        dataset_reader=cast(Any, dataset_reader),
        model_catalog=cast(Any, model_catalog),
    )


@pytest.mark.asyncio
async def test_collection_validates_predictions_before_atomic_create() -> None:
    repository = Mock(spec=PredictionRepository)
    repository.get_platform_predictions_by_ids = AsyncMock(
        return_value={
            "prediction-1": PlatformPrediction(
                id="prediction-1",
                org_id="org-1",
                dataset_id="dataset-1",
                sample_id="sample-1",
                model_id="model-1",
                predicted_label="cat",
                created_by="user-1",
            )
        }
    )
    repository.create_prediction_collection_with_items = AsyncMock(
        side_effect=lambda collection, _items: collection
    )

    collection = await _service(repository).create_prediction_collection(
        dataset_id="dataset-1",
        model_id="model-1",
        org_id="org-1",
        created_by="user-1",
        prediction_ids=["prediction-1"],
        name="review set",
    )

    assert collection.dataset_id == "dataset-1"
    repository.get_platform_predictions_by_ids.assert_awaited_once_with(
        ["prediction-1"],
        "org-1",
    )
    repository.create_prediction_collection_with_items.assert_awaited_once()


@pytest.mark.asyncio
async def test_collection_missing_prediction_creates_no_partial_record() -> None:
    repository = Mock(spec=PredictionRepository)
    repository.get_platform_predictions_by_ids = AsyncMock(return_value={})
    repository.create_prediction_collection_with_items = AsyncMock()

    with pytest.raises(ValueError, match="Prediction not found: prediction-1"):
        await _service(repository).create_prediction_collection(
            dataset_id="dataset-1",
            model_id="model-1",
            org_id="org-1",
            created_by="user-1",
            prediction_ids=["prediction-1"],
            name="review set",
        )

    repository.create_prediction_collection_with_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_collection_rejects_duplicate_prediction_ids() -> None:
    repository = Mock(spec=PredictionRepository)
    repository.get_platform_predictions_by_ids = AsyncMock()
    repository.create_prediction_collection_with_items = AsyncMock()

    with pytest.raises(ValueError, match="duplicate prediction IDs"):
        await _service(repository).create_prediction_collection(
            dataset_id="dataset-1",
            model_id="model-1",
            org_id="org-1",
            created_by="user-1",
            prediction_ids=["prediction-1", "prediction-1"],
            name="review set",
        )

    repository.get_platform_predictions_by_ids.assert_not_awaited()
    repository.create_prediction_collection_with_items.assert_not_awaited()


def _review_service(
    repository: PredictionRepository,
    *,
    sample: SampleRow | None,
) -> tuple[PredictionReviewService, AsyncMock, AsyncMock]:
    samples_by_id = {sample.sample_id: sample} if sample is not None else {}
    storage = SimpleNamespace(
        get_samples_by_id=AsyncMock(return_value=samples_by_id)
    )
    storage_factory = SimpleNamespace(open=AsyncMock(return_value=storage))
    dataset_reader = SimpleNamespace(create_annotation=AsyncMock())
    service = PredictionReviewService(
        repository=repository,
        config=cast(Any, SimpleNamespace()),
        dataset_storage_factory=cast(Any, storage_factory),
        dataset_reader=cast(Any, dataset_reader),
        model_catalog=cast(Any, SimpleNamespace()),
    )
    return service, storage_factory.open, dataset_reader.create_annotation


@pytest.mark.asyncio
async def test_review_rejects_missing_ls_task_before_writes() -> None:
    repository = Mock(spec=PredictionRepository)
    repository.get_review_action = AsyncMock(
        return_value=PredictionReviewAction(
            dataset_id="dataset-1",
            model_id="model-1",
            created_by="user-1",
        )
    )
    repository.create_annotation_versions_bulk = AsyncMock()
    service, _open_storage, create_annotation = _review_service(
        repository,
        sample=SampleRow(
            sample_id="sample-1",
            dataset_id="dataset-1",
            ls_task_id=None,
        ),
    )

    with pytest.raises(ValueError, match="missing Label Studio tasks: sample-1"):
        await service.save_review_annotations(
            review_action_id="review-1",
            items=[
                ReviewAnnotationCommand(
                    sample_id="sample-1",
                    predicted_label="cat",
                    final_label="dog",
                )
            ],
            created_by="user-1",
            org_id="org-1",
        )

    create_annotation.assert_not_awaited()
    repository.create_annotation_versions_bulk.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_does_not_fallback_to_local_write_when_ls_fails() -> None:
    repository = Mock(spec=PredictionRepository)
    repository.get_review_action = AsyncMock(
        return_value=PredictionReviewAction(
            dataset_id="dataset-1",
            model_id="model-1",
            created_by="user-1",
        )
    )
    repository.create_annotation_versions_bulk = AsyncMock()
    service, _open_storage, create_annotation = _review_service(
        repository,
        sample=SampleRow(
            sample_id="sample-1",
            dataset_id="dataset-1",
            ls_task_id=42,
        ),
    )
    ls_client = SimpleNamespace(
        create_annotation=AsyncMock(side_effect=LabelStudioError("unavailable"))
    )
    service._ls_client = cast(Any, ls_client)

    with pytest.raises(ValueError, match="Label Studio annotation failed"):
        await service.save_review_annotations(
            review_action_id="review-1",
            items=[
                ReviewAnnotationCommand(
                    sample_id="sample-1",
                    predicted_label="cat",
                    final_label="dog",
                )
            ],
            created_by="user-1",
            org_id="org-1",
        )

    create_annotation.assert_not_awaited()
    repository.create_annotation_versions_bulk.assert_not_awaited()
