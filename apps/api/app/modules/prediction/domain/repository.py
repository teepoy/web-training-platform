from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import (
    Annotation,
    AnnotationVersion,
    Dataset,
    JobStatus,
    Model,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionEvent,
    PredictionJob,
    PredictionReviewAction,
    Sample,
    TrainingJob,
)


class PredictionRepository(Protocol):
    async def get_model(self, artifact_id: str, org_id: str) -> Model | None: ...

    async def get_job(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> TrainingJob | None: ...

    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Dataset | None: ...

    async def get_sample(self, sample_id: str) -> Sample | None: ...

    async def list_samples(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Sample], int]: ...

    async def create_annotation(self, annotation: Annotation) -> Annotation: ...

    async def get_annotation(self, annotation_id: str) -> Annotation | None: ...

    async def create_prediction_job(
        self,
        job: PredictionJob,
        org_id: str | None = None,
    ) -> PredictionJob: ...

    async def set_prediction_job_external_id(
        self,
        job_id: str,
        external_job_id: str,
    ) -> None: ...

    async def update_prediction_job_status(
        self,
        job_id: str,
        status: JobStatus,
        summary: dict | None = None,
    ) -> None: ...

    async def get_prediction_job(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> PredictionJob | None: ...

    async def list_prediction_jobs(
        self,
        org_id: str | None = None,
    ) -> list[PredictionJob]: ...

    async def add_prediction_event(self, event: PredictionEvent) -> None: ...

    async def list_prediction_events(self, job_id: str) -> list[PredictionEvent]: ...

    async def create_platform_prediction(
        self,
        prediction: PlatformPrediction,
    ) -> PlatformPrediction: ...

    async def get_platform_prediction(
        self,
        prediction_id: str,
        org_id: str | None = None,
    ) -> PlatformPrediction | None: ...

    async def list_platform_predictions_for_sample(
        self,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
    ) -> list[PlatformPrediction]: ...

    async def list_platform_predictions_for_job(
        self,
        job_id: str,
        org_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[PlatformPrediction]: ...

    async def create_prediction_collection(
        self,
        collection: PredictionCollection,
    ) -> PredictionCollection: ...

    async def get_prediction_collection(
        self,
        collection_id: str,
        org_id: str | None = None,
    ) -> PredictionCollection | None: ...

    async def list_prediction_collections(
        self,
        dataset_id: str,
        org_id: str,
    ) -> list[PredictionCollection]: ...

    async def add_prediction_collection_items(
        self,
        items: list[PredictionCollectionItem],
    ) -> list[PredictionCollectionItem]: ...

    async def list_prediction_collection_predictions(
        self,
        collection_id: str,
        org_id: str,
    ) -> list[PlatformPrediction]: ...

    async def create_review_action(
        self,
        action: PredictionReviewAction,
    ) -> PredictionReviewAction: ...

    async def get_review_action(
        self, action_id: str
    ) -> PredictionReviewAction | None: ...

    async def list_review_actions(
        self,
        dataset_id: str,
    ) -> list[PredictionReviewAction]: ...

    async def delete_review_action(self, action_id: str) -> bool: ...

    async def create_annotation_versions_bulk(
        self,
        versions: list[AnnotationVersion],
    ) -> list[AnnotationVersion]: ...

    async def list_annotation_versions(
        self,
        review_action_id: str,
    ) -> list[AnnotationVersion]: ...
