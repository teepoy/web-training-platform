from __future__ import annotations

from typing import Protocol

from app.modules.prediction.domain.results import (
    BatchPredictionResult,
    PredictionResult,
)
from app.modules.prediction.domain.review import ReviewAnnotationCommand
from app.modules.prediction.domain.submission import PredictionJobCommand
from app.shared.api.schemas import (
    Annotation,
    AnnotationVersion,
    PredictionCollection,
    PredictionJob,
    PredictionReviewAction,
)


class PredictionExecutionPort(Protocol):
    async def submit_job(self, command: PredictionJobCommand) -> PredictionJob: ...

    async def cancel_job(self, job_id: str, org_id: str | None = None) -> bool: ...


class PredictionRuntimePort(Protocol):
    async def run_prediction(
        self,
        model_id: str,
        dataset_id: str,
        org_id: str,
        sample_ids: list[str] | None = None,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
        predictor_id: str | None = None,
    ) -> BatchPredictionResult: ...

    async def predict_single(
        self,
        *,
        model_id: str,
        dataset_id: str,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
        predictor_id: str | None = None,
    ) -> PredictionResult: ...


class PredictionQueryPort(Protocol):
    async def list_predictions_for_sample(
        self,
        *,
        sample_id: str,
        org_id: str,
        dataset_id: str | None = None,
        model_version: str | None = None,
    ) -> list[PredictionResult]: ...

    async def list_predictions_for_job(
        self,
        job_id: str,
        org_id: str,
        offset: int = 0,
        limit: int = 1000,
    ) -> list[PredictionResult]: ...


class PredictionCollectionPort(Protocol):
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
    ) -> PredictionCollection: ...

    async def sync_prediction_collection_to_label_studio(
        self,
        collection_id: str,
        org_id: str,
        sync_tag: str | None = None,
    ) -> tuple[PredictionCollection, int, int, list[str]]: ...


class PredictionReviewPort(Protocol):
    async def create_review_action(
        self,
        dataset_id: str,
        model_id: str,
        org_id: str,
        created_by: str,
        model_version: str | None = None,
        collection_id: str | None = None,
        sync_tag: str | None = None,
    ) -> PredictionReviewAction: ...

    async def save_review_annotations(
        self,
        review_action_id: str,
        items: list[ReviewAnnotationCommand],
        created_by: str,
        org_id: str,
    ) -> tuple[list[Annotation], list[AnnotationVersion]]: ...


__all__ = [
    "PredictionExecutionPort",
    "PredictionCollectionPort",
    "PredictionQueryPort",
    "PredictionReviewPort",
    "PredictionRuntimePort",
]
