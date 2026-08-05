from __future__ import annotations

from typing import Protocol

from app.shared.api.schemas import (
    AnnotationVersion,
    JobStatus,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionEvent,
    PredictionJob,
    PredictionReviewAction,
)


class PredictionRepository(Protocol):
    async def has_active_jobs(self, *, dataset_id: str, org_id: str) -> bool: ...

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
        dataset_id: str | None = None,
    ) -> list[PredictionJob]: ...

    async def list_prediction_jobs_paginated(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        collection_id: str | None = None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PredictionJob], int]: ...

    async def add_prediction_event(self, event: PredictionEvent) -> None: ...

    async def list_prediction_events(self, job_id: str) -> list[PredictionEvent]: ...

    async def list_prediction_events_paginated(
        self,
        job_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PredictionEvent], int]: ...

    async def create_platform_predictions_bulk(
        self,
        predictions: list[PlatformPrediction],
    ) -> list[PlatformPrediction]: ...

    async def get_platform_prediction(
        self,
        prediction_id: str,
        org_id: str | None = None,
    ) -> PlatformPrediction | None: ...

    async def get_platform_predictions_by_ids(
        self,
        prediction_ids: list[str],
        org_id: str,
    ) -> dict[str, PlatformPrediction]: ...

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

    async def list_prediction_collections_paginated(
        self,
        dataset_id: str,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PredictionCollection], int]: ...

    async def add_prediction_collection_items(
        self,
        items: list[PredictionCollectionItem],
    ) -> list[PredictionCollectionItem]: ...

    async def create_prediction_collection_with_items(
        self,
        collection: PredictionCollection,
        items: list[PredictionCollectionItem],
    ) -> PredictionCollection: ...

    async def list_prediction_collection_predictions(
        self,
        collection_id: str,
        org_id: str,
    ) -> list[PlatformPrediction]: ...

    async def list_prediction_ids_by_collection(
        self,
        collection_ids: list[str],
        org_id: str,
    ) -> dict[str, list[str]]: ...

    async def create_review_action(
        self,
        action: PredictionReviewAction,
    ) -> PredictionReviewAction: ...

    async def get_review_action(
        self,
        action_id: str,
        org_id: str,
    ) -> PredictionReviewAction | None: ...

    async def list_review_actions(
        self,
        dataset_id: str,
        org_id: str,
    ) -> list[PredictionReviewAction]: ...

    async def list_review_actions_paginated(
        self,
        dataset_id: str,
        org_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PredictionReviewAction], int]: ...

    async def delete_review_action(self, action_id: str, org_id: str) -> bool: ...

    async def create_annotation_versions_bulk(
        self,
        versions: list[AnnotationVersion],
    ) -> list[AnnotationVersion]: ...

    async def list_annotation_versions(
        self,
        review_action_id: str,
    ) -> list[AnnotationVersion]: ...

    async def list_annotation_versions_paginated(
        self,
        review_action_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AnnotationVersion], int]: ...
