from __future__ import annotations

from datetime import UTC, datetime

from injector import inject

from app.core.config import AppConfig
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.prediction.domain.review import ReviewAnnotationCommand
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.shared.api.schemas import (
    Annotation,
    AnnotationVersion,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionReviewAction,
)
from app.shared.application.compatibility import validate_model_review
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.label_studio.client import (
    LabelStudioClient as RealLabelStudioClient,
)
from app.shared.infrastructure.label_studio.client import (
    LabelStudioError,
    platform_annotation_to_ls,
    platform_prediction_to_ls,
    platform_text_prediction_to_ls,
)


class PredictionReviewService:
    """Own prediction collections, Label Studio sync, and review persistence."""

    @inject
    def __init__(
        self,
        repository: PredictionRepository,
        config: AppConfig,
        dataset_storage_factory: DatasetStorageFactoryPort,
        dataset_reader: DatasetReader,
        model_catalog: ModelCatalogPort,
    ) -> None:
        self._repository = repository
        self._config = config
        self._ls_client: LabelStudioClient | None = None
        self._dataset_storage_factory = dataset_storage_factory
        self._dataset_reader = dataset_reader
        self._model_catalog = model_catalog

    def _get_ls_client(self) -> LabelStudioClient:
        if self._ls_client is None:
            ls_cfg = self._config.label_studio
            if not ls_cfg.url:
                raise ValueError("Label Studio URL not configured")
            self._ls_client = RealLabelStudioClient(
                url=ls_cfg.url,
                api_key=ls_cfg.api_key,
            )
        return self._ls_client

    async def create_prediction_collection(
        self,
        dataset_id: str,
        model_id: str,
        org_id: str,
        created_by: str,
        prediction_ids: list[str],
        name: str,
        model_version: str | None = None,
        target: str = "image_classification",
        source_job_id: str | None = None,
    ) -> PredictionCollection:
        dataset = await self._dataset_reader.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        model = await self._model_catalog.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        unique_prediction_ids = list(dict.fromkeys(prediction_ids))
        if len(unique_prediction_ids) != len(prediction_ids):
            raise ValueError("Prediction collection contains duplicate prediction IDs")
        predictions_by_id = await self._repository.get_platform_predictions_by_ids(
            unique_prediction_ids,
            org_id,
        )
        for prediction_id in unique_prediction_ids:
            prediction = predictions_by_id.get(prediction_id)
            if prediction is None:
                raise ValueError(f"Prediction not found: {prediction_id}")
            if prediction.dataset_id != dataset_id:
                raise ValueError(
                    f"Prediction {prediction_id} does not belong to dataset {dataset_id}"
                )

        collection = PredictionCollection(
            org_id=org_id,
            dataset_id=dataset_id,
            model_id=model_id,
            name=name,
            model_version=model_version,
            target=target,
            source_job_id=source_job_id,
            created_by=created_by,
        )
        items = [
            PredictionCollectionItem(
                collection_id=collection.id,
                prediction_id=prediction_id,
            )
            for prediction_id in unique_prediction_ids
        ]
        return await self._repository.create_prediction_collection_with_items(
            collection,
            items,
        )

    async def sync_prediction_collection_to_label_studio(
        self,
        collection_id: str,
        org_id: str,
        sync_tag: str | None = None,
    ) -> tuple[PredictionCollection, int, int, list[str]]:
        collection = await self._repository.get_prediction_collection(
            collection_id,
            org_id=org_id,
        )
        if collection is None:
            raise ValueError(f"Prediction collection not found: {collection_id}")
        dataset = await self._dataset_reader.get_dataset(collection.dataset_id, org_id)
        if dataset is None or dataset.ls_project_id is None:
            raise ValueError(
                f"Dataset not found or missing Label Studio project: {collection.dataset_id}"
            )
        predictions = await self._repository.list_prediction_collection_predictions(
            collection_id,
            org_id,
        )
        sync_tag_value = (
            sync_tag
            or collection.sync_tag
            or f"sync-{collection.id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        )
        sample_ids = [prediction.sample_id for prediction in predictions]
        storage = await self._dataset_storage_factory.open(
            dataset_id=collection.dataset_id,
            org_id=org_id,
        )
        samples_by_id = await storage.get_samples_by_id(sample_ids)
        ls_client = self._get_ls_client()

        successful = 0
        failed = 0
        errors: list[str] = []
        for prediction in predictions:
            sample = samples_by_id.get(prediction.sample_id)
            if sample is None or sample.ls_task_id is None:
                failed += 1
                errors.append(f"sample {prediction.sample_id} has no Label Studio task")
                continue
            if prediction.error:
                failed += 1
                errors.append(f"prediction {prediction.id} has runtime error")
                continue
            try:
                ls_result = (
                    platform_text_prediction_to_ls(prediction.predicted_label)
                    if prediction.target == "vqa"
                    else platform_prediction_to_ls(prediction.predicted_label)
                )
                await ls_client.create_prediction(
                    task_id=sample.ls_task_id,
                    result=ls_result,
                    model_version=sync_tag_value,
                    score=prediction.confidence,
                )
                successful += 1
            except LabelStudioError as exc:
                failed += 1
                errors.append(f"prediction {prediction.id}: {exc}")

        return (
            collection.model_copy(update={"sync_tag": sync_tag_value}),
            successful,
            failed,
            errors,
        )

    async def create_review_action(
        self,
        dataset_id: str,
        model_id: str,
        org_id: str,
        created_by: str,
        model_version: str | None = None,
        collection_id: str | None = None,
        sync_tag: str | None = None,
    ) -> PredictionReviewAction:
        dataset = await self._dataset_reader.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        model = await self._model_catalog.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        validate_model_review(
            dataset,
            model.metadata if isinstance(model.metadata, dict) else {},
        )
        action = PredictionReviewAction(
            dataset_id=dataset_id,
            model_id=model_id,
            model_version=model_version,
            collection_id=collection_id,
            sync_tag=sync_tag,
            created_by=created_by,
        )
        return await self._repository.create_review_action(action)

    async def save_review_annotations(
        self,
        review_action_id: str,
        items: list[ReviewAnnotationCommand],
        created_by: str,
        org_id: str,
    ) -> tuple[list[Annotation], list[AnnotationVersion]]:
        action = await self._repository.get_review_action(review_action_id, org_id)
        if action is None:
            raise ValueError(f"Review action not found: {review_action_id}")
        if not items:
            raise ValueError("Review annotations must not be empty")

        sample_ids = [item.sample_id for item in items]
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError("Review annotations contain duplicate sample IDs")
        storage = await self._dataset_storage_factory.open(
            dataset_id=action.dataset_id,
            org_id=org_id,
        )
        samples_by_id = await storage.get_samples_by_id(sample_ids)
        missing_sample_ids = [
            sample_id
            for sample_id in sample_ids
            if sample_id not in samples_by_id
            or samples_by_id[sample_id].ls_task_id is None
        ]
        if missing_sample_ids:
            joined = ", ".join(dict.fromkeys(missing_sample_ids))
            raise ValueError(f"Review samples are missing Label Studio tasks: {joined}")

        ls_client = self._get_ls_client()
        for item in items:
            sample = samples_by_id[item.sample_id]
            assert sample.ls_task_id is not None
            try:
                await ls_client.create_annotation(
                    sample.ls_task_id,
                    platform_annotation_to_ls(item.final_label),
                )
            except LabelStudioError as exc:
                raise ValueError(
                    f"Label Studio annotation failed for sample {item.sample_id}: {exc}"
                ) from exc

        annotations: list[Annotation] = []
        versions: list[AnnotationVersion] = []
        for item in items:
            annotation = await self._dataset_reader.create_annotation(
                Annotation(
                    sample_id=item.sample_id,
                    label=item.final_label,
                    created_by=created_by,
                )
            )
            annotations.append(annotation)
            versions.append(
                AnnotationVersion(
                    review_action_id=review_action_id,
                    annotation_id=annotation.id,
                    prediction_id=item.prediction_id,
                    predicted_label=item.predicted_label,
                    final_label=item.final_label,
                    confidence=item.confidence,
                )
            )

        versions = await self._repository.create_annotation_versions_bulk(versions)
        return annotations, versions
