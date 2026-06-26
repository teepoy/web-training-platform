from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.api.schemas import (
    AnnotationVersion,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionEvent,
    PredictionJob,
    PredictionReviewAction,
)
from app.shared.api.schemas import JobStatus
from app.shared.db.models.auth import OrganizationORM
from app.shared.db.models.datasets import AnnotationVersionORM
from app.shared.db.models.prediction import (
    PlatformPredictionORM,
    PredictionCollectionItemORM,
    PredictionCollectionORM,
    PredictionEventORM,
    PredictionJobORM,
    PredictionReviewActionORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _assert_not_none(value: str | None) -> str:
    assert value is not None
    return value


async def _org_name_for(session: AsyncSession, org_id: str | None) -> str:
    if not org_id:
        return ""
    org_row = await session.get(OrganizationORM, org_id)
    return "" if org_row is None else org_row.name


class PredictionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_prediction_job(
        self, job: PredictionJob, org_id: str | None = None
    ) -> PredictionJob:
        org_id = org_id or job.org_id
        if org_id is None:
            raise ValueError("org_id is required for create_prediction_job")
        async with self.session_factory() as session:
            org_name = await _org_name_for(session, org_id)
            session.add(
                PredictionJobORM(
                    id=job.id,
                    org_id=org_id,
                    dataset_id=job.dataset_id,
                    model_id=job.model_id,
                    status=job.status.value,
                    target=job.target,
                    model_version=job.model_version,
                    sample_ids=job.sample_ids,
                    summary_json=job.summary,
                    created_by=job.created_by,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    external_job_id=job.external_job_id,
                )
            )
            await session.commit()
        return job.model_copy(update={"org_id": org_id, "org_name": org_name})

    async def set_prediction_job_external_id(
        self, job_id: str, external_job_id: str
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(PredictionJobORM, job_id)
            if row is None:
                return
            row.external_job_id = external_job_id
            row.updated_at = _utcnow()
            await session.commit()

    async def update_prediction_job_status(
        self, job_id: str, status: JobStatus, summary: dict | None = None
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(PredictionJobORM, job_id)
            if row is None:
                return
            row.status = status.value
            row.updated_at = _utcnow()
            if summary is not None:
                row.summary_json = summary
            await session.commit()

    async def get_prediction_job(
        self, job_id: str, org_id: str | None = None
    ) -> PredictionJob | None:
        async with self.session_factory() as session:
            row = await session.get(PredictionJobORM, job_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            return PredictionJob(
                id=row.id,
                org_id=row.org_id,
                org_name=await _org_name_for(session, row.org_id),
                dataset_id=_assert_not_none(row.dataset_id),
                model_id=row.model_id,
                status=cast(JobStatus, row.status),
                created_by=row.created_by,
                target=row.target,
                model_version=row.model_version,
                created_at=row.created_at,
                updated_at=row.updated_at,
                external_job_id=row.external_job_id,
                sample_ids=row.sample_ids,
                summary=row.summary_json or {},
            )

    async def list_prediction_jobs(
        self, org_id: str | None = None, dataset_id: str | None = None
    ) -> list[PredictionJob]:
        async with self.session_factory() as session:
            stmt = select(PredictionJobORM).order_by(PredictionJobORM.created_at.desc())
            if org_id is not None:
                stmt = stmt.where(PredictionJobORM.org_id == org_id)
            if dataset_id is not None:
                stmt = stmt.where(PredictionJobORM.dataset_id == dataset_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PredictionJob(
                    id=row.id,
                    org_id=row.org_id,
                    org_name=await _org_name_for(session, row.org_id),
                    dataset_id=_assert_not_none(row.dataset_id),
                    model_id=row.model_id,
                    status=cast(JobStatus, row.status),
                    created_by=row.created_by,
                    target=row.target,
                    model_version=row.model_version,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    external_job_id=row.external_job_id,
                    sample_ids=row.sample_ids,
                    summary=row.summary_json or {},
                )
                for row in rows
            ]

    async def add_prediction_event(self, event: PredictionEvent) -> None:
        async with self.session_factory() as session:
            session.add(
                PredictionEventORM(
                    job_id=event.job_id,
                    ts=event.ts,
                    level=event.level,
                    message=event.message,
                    payload=event.payload,
                )
            )
            await session.commit()

    async def list_prediction_events(self, job_id: str) -> list[PredictionEvent]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(PredictionEventORM)
                        .where(PredictionEventORM.job_id == job_id)
                        .order_by(PredictionEventORM.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            return [
                PredictionEvent(
                    job_id=r.job_id,
                    ts=r.ts,
                    level=r.level,
                    message=r.message,
                    payload=r.payload,
                )
                for r in rows
            ]

    async def create_platform_prediction(
        self, prediction: PlatformPrediction
    ) -> PlatformPrediction:
        async with self.session_factory() as session:
            session.add(
                PlatformPredictionORM(
                    id=prediction.id,
                    org_id=prediction.org_id,
                    dataset_id=prediction.dataset_id,
                    sample_id=prediction.sample_id,
                    model_id=prediction.model_id,
                    target=prediction.target,
                    job_id=prediction.job_id,
                    model_version=prediction.model_version,
                    predicted_label=prediction.predicted_label,
                    confidence=prediction.confidence,
                    all_scores_json=prediction.all_scores,
                    error=prediction.error,
                    created_by=prediction.created_by,
                    created_at=prediction.created_at,
                )
            )
            await session.commit()
        return prediction

    async def create_platform_predictions_bulk(
        self, predictions: list[PlatformPrediction]
    ) -> list[PlatformPrediction]:
        if not predictions:
            return []
        async with self.session_factory() as session:
            for prediction in predictions:
                session.add(
                    PlatformPredictionORM(
                        id=prediction.id,
                        org_id=prediction.org_id,
                        dataset_id=prediction.dataset_id,
                        sample_id=prediction.sample_id,
                        model_id=prediction.model_id,
                        target=prediction.target,
                        job_id=prediction.job_id,
                        model_version=prediction.model_version,
                        predicted_label=prediction.predicted_label,
                        confidence=prediction.confidence,
                        all_scores_json=prediction.all_scores,
                        error=prediction.error,
                        created_by=prediction.created_by,
                        created_at=prediction.created_at,
                    )
                )
            await session.commit()
        return predictions

    async def get_platform_prediction(
        self, prediction_id: str, org_id: str | None = None
    ) -> PlatformPrediction | None:
        async with self.session_factory() as session:
            row = await session.get(PlatformPredictionORM, prediction_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            return PlatformPrediction(
                id=row.id,
                org_id=row.org_id,
                dataset_id=row.dataset_id,
                sample_id=row.sample_id,
                model_id=row.model_id,
                target=row.target,
                job_id=row.job_id,
                model_version=row.model_version,
                predicted_label=row.predicted_label,
                confidence=row.confidence,
                all_scores=row.all_scores_json,
                error=row.error,
                created_by=row.created_by,
                created_at=row.created_at,
            )

    async def list_platform_predictions_for_sample(
        self,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
    ) -> list[PlatformPrediction]:
        async with self.session_factory() as session:
            stmt = (
                select(PlatformPredictionORM)
                .where(PlatformPredictionORM.sample_id == sample_id)
                .where(PlatformPredictionORM.org_id == org_id)
                .order_by(PlatformPredictionORM.created_at.desc())
            )
            if model_version is not None:
                stmt = stmt.where(PlatformPredictionORM.model_version == model_version)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PlatformPrediction(
                    id=row.id,
                    org_id=row.org_id,
                    dataset_id=row.dataset_id,
                    sample_id=row.sample_id,
                    model_id=row.model_id,
                    target=row.target,
                    job_id=row.job_id,
                    model_version=row.model_version,
                    predicted_label=row.predicted_label,
                    confidence=row.confidence,
                    all_scores=row.all_scores_json,
                    error=row.error,
                    created_by=row.created_by,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def list_platform_predictions_for_job(
        self, job_id: str, org_id: str, offset: int = 0, limit: int | None = None
    ) -> list[PlatformPrediction]:
        async with self.session_factory() as session:
            stmt = (
                select(PlatformPredictionORM)
                .where(PlatformPredictionORM.job_id == job_id)
                .where(PlatformPredictionORM.org_id == org_id)
                .order_by(PlatformPredictionORM.created_at.asc())
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PlatformPrediction(
                    id=row.id,
                    org_id=row.org_id,
                    dataset_id=row.dataset_id,
                    sample_id=row.sample_id,
                    model_id=row.model_id,
                    target=row.target,
                    job_id=row.job_id,
                    model_version=row.model_version,
                    predicted_label=row.predicted_label,
                    confidence=row.confidence,
                    all_scores=row.all_scores_json,
                    error=row.error,
                    created_by=row.created_by,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def create_prediction_collection(
        self, collection: PredictionCollection
    ) -> PredictionCollection:
        async with self.session_factory() as session:
            session.add(
                PredictionCollectionORM(
                    id=collection.id,
                    org_id=collection.org_id,
                    dataset_id=collection.dataset_id,
                    model_id=collection.model_id,
                    name=collection.name,
                    model_version=collection.model_version,
                    target=collection.target,
                    source_job_id=collection.source_job_id,
                    sync_tag=collection.sync_tag,
                    created_by=collection.created_by,
                    created_at=collection.created_at,
                )
            )
            await session.commit()
        return collection

    async def get_prediction_collection(
        self, collection_id: str, org_id: str | None = None
    ) -> PredictionCollection | None:
        async with self.session_factory() as session:
            row = await session.get(PredictionCollectionORM, collection_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            return PredictionCollection(
                id=row.id,
                org_id=row.org_id,
                dataset_id=row.dataset_id,
                model_id=row.model_id,
                name=row.name,
                model_version=row.model_version,
                target=row.target,
                source_job_id=row.source_job_id,
                sync_tag=row.sync_tag,
                created_by=row.created_by,
                created_at=row.created_at,
            )

    async def list_prediction_collections(
        self, dataset_id: str, org_id: str
    ) -> list[PredictionCollection]:
        async with self.session_factory() as session:
            stmt = (
                select(PredictionCollectionORM)
                .where(PredictionCollectionORM.dataset_id == dataset_id)
                .where(PredictionCollectionORM.org_id == org_id)
                .order_by(PredictionCollectionORM.created_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PredictionCollection(
                    id=row.id,
                    org_id=row.org_id,
                    dataset_id=row.dataset_id,
                    model_id=row.model_id,
                    name=row.name,
                    model_version=row.model_version,
                    target=row.target,
                    source_job_id=row.source_job_id,
                    sync_tag=row.sync_tag,
                    created_by=row.created_by,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def add_prediction_collection_items(
        self, items: list[PredictionCollectionItem]
    ) -> list[PredictionCollectionItem]:
        if not items:
            return []
        async with self.session_factory() as session:
            for item in items:
                session.add(
                    PredictionCollectionItemORM(
                        collection_id=item.collection_id,
                        prediction_id=item.prediction_id,
                        created_at=item.created_at,
                    )
                )
            await session.commit()
        return items

    async def list_prediction_collection_predictions(
        self, collection_id: str, org_id: str
    ) -> list[PlatformPrediction]:
        async with self.session_factory() as session:
            stmt = (
                select(PlatformPredictionORM)
                .join(
                    PredictionCollectionItemORM,
                    PredictionCollectionItemORM.prediction_id
                    == PlatformPredictionORM.id,
                )
                .where(PredictionCollectionItemORM.collection_id == collection_id)
                .where(PlatformPredictionORM.org_id == org_id)
                .order_by(PlatformPredictionORM.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PlatformPrediction(
                    id=row.id,
                    org_id=row.org_id,
                    dataset_id=row.dataset_id,
                    sample_id=row.sample_id,
                    model_id=row.model_id,
                    target=row.target,
                    job_id=row.job_id,
                    model_version=row.model_version,
                    predicted_label=row.predicted_label,
                    confidence=row.confidence,
                    all_scores=row.all_scores_json,
                    error=row.error,
                    created_by=row.created_by,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def create_review_action(
        self, action: PredictionReviewAction
    ) -> PredictionReviewAction:
        async with self.session_factory() as session:
            session.add(
                PredictionReviewActionORM(
                    id=action.id,
                    dataset_id=action.dataset_id,
                    model_id=action.model_id,
                    model_version=action.model_version,
                    collection_id=action.collection_id,
                    sync_tag=action.sync_tag,
                    created_by=action.created_by,
                    created_at=action.created_at,
                )
            )
            await session.commit()
        return action

    async def get_review_action(self, action_id: str) -> PredictionReviewAction | None:
        async with self.session_factory() as session:
            row = await session.get(PredictionReviewActionORM, action_id)
            if row is None:
                return None
            return PredictionReviewAction(
                id=row.id,
                dataset_id=row.dataset_id,
                model_id=row.model_id,
                model_version=row.model_version,
                collection_id=row.collection_id,
                sync_tag=row.sync_tag,
                created_by=row.created_by,
                created_at=row.created_at,
            )

    async def list_review_actions(
        self, dataset_id: str
    ) -> list[PredictionReviewAction]:
        async with self.session_factory() as session:
            stmt = (
                select(PredictionReviewActionORM)
                .where(PredictionReviewActionORM.dataset_id == dataset_id)
                .order_by(PredictionReviewActionORM.created_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PredictionReviewAction(
                    id=r.id,
                    dataset_id=r.dataset_id,
                    model_id=r.model_id,
                    model_version=r.model_version,
                    collection_id=r.collection_id,
                    sync_tag=r.sync_tag,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def delete_review_action(self, action_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(PredictionReviewActionORM, action_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Annotation Version CRUD
    # ------------------------------------------------------------------

    async def create_annotation_version(
        self, version: AnnotationVersion
    ) -> AnnotationVersion:
        async with self.session_factory() as session:
            session.add(
                AnnotationVersionORM(
                    id=version.id,
                    review_action_id=version.review_action_id,
                    annotation_id=version.annotation_id,
                    prediction_id=version.prediction_id,
                    predicted_label=version.predicted_label,
                    final_label=version.final_label,
                    confidence=version.confidence,
                    created_at=version.created_at,
                )
            )
            await session.commit()
        return version

    async def create_annotation_versions_bulk(
        self, versions: list[AnnotationVersion]
    ) -> list[AnnotationVersion]:
        async with self.session_factory() as session:
            for v in versions:
                session.add(
                    AnnotationVersionORM(
                        id=v.id,
                        review_action_id=v.review_action_id,
                        annotation_id=v.annotation_id,
                        prediction_id=v.prediction_id,
                        predicted_label=v.predicted_label,
                        final_label=v.final_label,
                        confidence=v.confidence,
                        created_at=v.created_at,
                    )
                )
            await session.commit()
        return versions

    async def list_annotation_versions(
        self, review_action_id: str
    ) -> list[AnnotationVersion]:
        async with self.session_factory() as session:
            stmt = (
                select(AnnotationVersionORM)
                .where(AnnotationVersionORM.review_action_id == review_action_id)
                .order_by(AnnotationVersionORM.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                AnnotationVersion(
                    id=r.id,
                    review_action_id=r.review_action_id,
                    annotation_id=r.annotation_id,
                    prediction_id=r.prediction_id,
                    predicted_label=r.predicted_label,
                    final_label=r.final_label,
                    confidence=r.confidence,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def get_annotation_version(self, version_id: str) -> AnnotationVersion | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationVersionORM, version_id)
            if row is None:
                return None
            return AnnotationVersion(
                id=row.id,
                review_action_id=row.review_action_id,
                annotation_id=row.annotation_id,
                prediction_id=row.prediction_id,
                predicted_label=row.predicted_label,
                final_label=row.final_label,
                confidence=row.confidence,
                created_at=row.created_at,
            )
