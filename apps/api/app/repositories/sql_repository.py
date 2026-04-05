from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AnnotationORM,
    ArtifactORM,
    DatasetORM,
    JobUserStateORM,
    OrgMembershipORM,
    OrganizationORM,
    PersonalAccessTokenORM,
    PredictionEditORM,
    PredictionORM,
    SampleFeatureORM,
    SampleORM,
    ScheduleORM,
    TrainingEventORM,
    TrainingJobORM,
    TrainingPresetORM,
    UserORM,
)
from app.domain.models import (
    Annotation,
    ArtifactRef,
    Dataset,
    DEFAULT_ORG_ID,
    PredictionEdit,
    PredictionResult,
    Sample,
    SampleFeature,
    TrainingEvent,
    TrainingJob,
    TrainingPreset,
)
from app.domain.types import JobStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_dataset(self, dataset: Dataset, org_id: str | None = None) -> Dataset:
        org_id = org_id or dataset.org_id or DEFAULT_ORG_ID
        async with self.session_factory() as session:
            row = DatasetORM(
                id=dataset.id,
                org_id=org_id,
                name=dataset.name,
                dataset_type=dataset.dataset_type.value,
                task_spec=dataset.task_spec.model_dump(mode="json"),
                created_at=dataset.created_at,
                embed_config=dataset.embed_config or None,
                ls_project_id=dataset.ls_project_id,
            )
            session.add(row)
            await session.commit()
        return dataset.model_copy(update={"org_id": org_id})

    async def list_datasets(self, org_id: str | None = None) -> list[Dataset]:
        async with self.session_factory() as session:
            stmt = select(DatasetORM).order_by(DatasetORM.created_at.desc())
            if org_id is not None:
                stmt = stmt.where(or_(DatasetORM.org_id == org_id, DatasetORM.is_public == True))  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Dataset(
                    id=r.id,
                    org_id=r.org_id,
                    name=r.name,
                    dataset_type=r.dataset_type,
                    task_spec=r.task_spec,
                    created_at=r.created_at,
                    embed_config=r.embed_config or {},
                    ls_project_id=r.ls_project_id,
                )
                for r in rows
            ]

    async def get_dataset(self, dataset_id: str, org_id: str | None = None) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
            return Dataset(
                id=row.id,
                org_id=row.org_id,
                name=row.name,
                dataset_type=row.dataset_type,
                task_spec=row.task_spec,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
            )

    async def update_dataset_embed_config(self, dataset_id: str, embed_config: dict) -> None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is not None:
                row.embed_config = embed_config
                await session.commit()

    async def set_dataset_public(self, dataset_id: str, is_public: bool) -> bool:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return False
            row.is_public = is_public
            await session.commit()
            return True

    async def set_job_public(self, job_id: str, is_public: bool) -> bool:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return False
            row.is_public = is_public
            await session.commit()
            return True

    async def update_dataset_ls_project_id(self, dataset_id: str, ls_project_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is not None:
                row.ls_project_id = ls_project_id
                await session.commit()

    async def create_sample(self, sample: Sample) -> Sample:
        async with self.session_factory() as session:
            session.add(
                SampleORM(
                    id=sample.id,
                    dataset_id=sample.dataset_id,
                    image_uris=sample.image_uris,
                    metadata_json=sample.metadata,
                    ls_task_id=sample.ls_task_id,
                )
            )
            await session.commit()
        return sample

    async def list_samples(self, dataset_id: str, offset: int = 0, limit: int = 50) -> tuple[list[Sample], int]:
        async with self.session_factory() as session:
            total = await session.scalar(
                select(func.count()).select_from(SampleORM).where(SampleORM.dataset_id == dataset_id)
            )
            rows = (
                await session.execute(
                    select(SampleORM)
                    .where(SampleORM.dataset_id == dataset_id)
                    .offset(offset)
                    .limit(limit)
                )
            ).scalars().all()
            return [
                Sample(
                    id=r.id,
                    dataset_id=r.dataset_id,
                    image_uris=r.image_uris,
                    metadata=r.metadata_json,
                    ls_task_id=r.ls_task_id,
                )
                for r in rows
            ], total or 0

    async def get_sample(self, sample_id: str) -> Sample | None:
        async with self.session_factory() as session:
            row = await session.get(SampleORM, sample_id)
            if row is None:
                return None
            return Sample(
                id=row.id,
                dataset_id=row.dataset_id,
                image_uris=row.image_uris,
                metadata=row.metadata_json,
                ls_task_id=row.ls_task_id,
            )

    async def list_samples_with_labels(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        label_filter: str | None = None,
        order_by: str = "id",
    ) -> tuple[list[dict], int]:
        """Return samples enriched with latest annotation and highest-score prediction.

        Uses subqueries to find:
        - Latest annotation per sample (MAX created_at)
        - Highest-score prediction per sample (MAX score)

        label_filter="__unlabeled__" → WHERE latest_annotation IS NULL
        label_filter="cat" → WHERE latest_annotation.label == "cat"
        """
        from sqlalchemy import alias, and_, null, outerjoin

        async with self.session_factory() as session:
            # Subquery: latest annotation per sample (max created_at)
            latest_ann_subq = (
                select(
                    AnnotationORM.sample_id.label("sample_id"),
                    func.max(AnnotationORM.created_at).label("max_created_at"),
                )
                .group_by(AnnotationORM.sample_id)
                .subquery("latest_ann_time")
            )

            # Subquery: highest-score prediction per sample (max score)
            best_pred_subq = (
                select(
                    PredictionORM.sample_id.label("sample_id"),
                    func.max(PredictionORM.score).label("max_score"),
                )
                .group_by(PredictionORM.sample_id)
                .subquery("best_pred_score")
            )

            # Alias AnnotationORM for the JOIN to get annotation details
            AnnAlias = alias(AnnotationORM.__table__, name="ann")
            # Alias PredictionORM for the JOIN to get prediction details
            PredAlias = alias(PredictionORM.__table__, name="pred")

            # Build base query: SampleORM LEFT JOIN to latest annotation, LEFT JOIN to best prediction
            stmt = (
                select(
                    SampleORM.id,
                    SampleORM.dataset_id,
                    SampleORM.image_uris,
                    SampleORM.metadata_json,
                    SampleORM.ls_task_id,
                    # Annotation fields
                    AnnAlias.c.id.label("ann_id"),
                    AnnAlias.c.label.label("ann_label"),
                    AnnAlias.c.created_by.label("ann_created_by"),
                    AnnAlias.c.created_at.label("ann_created_at"),
                    # Prediction fields
                    PredAlias.c.id.label("pred_id"),
                    PredAlias.c.predicted_label.label("pred_predicted_label"),
                    PredAlias.c.score.label("pred_score"),
                    PredAlias.c.model_artifact_id.label("pred_model_artifact_id"),
                )
                .where(SampleORM.dataset_id == dataset_id)
                .outerjoin(
                    latest_ann_subq,
                    latest_ann_subq.c.sample_id == SampleORM.id,
                )
                .outerjoin(
                    AnnAlias,
                    and_(
                        AnnAlias.c.sample_id == SampleORM.id,
                        AnnAlias.c.created_at == latest_ann_subq.c.max_created_at,
                    ),
                )
                .outerjoin(
                    best_pred_subq,
                    best_pred_subq.c.sample_id == SampleORM.id,
                )
                .outerjoin(
                    PredAlias,
                    and_(
                        PredAlias.c.sample_id == SampleORM.id,
                        PredAlias.c.score == best_pred_subq.c.max_score,
                    ),
                )
            )

            # Apply label filter
            if label_filter == "__unlabeled__":
                stmt = stmt.where(AnnAlias.c.id.is_(None))
            elif label_filter is not None:
                stmt = stmt.where(AnnAlias.c.label == label_filter)

            # Count total (before pagination)
            count_stmt = select(func.count()).select_from(stmt.subquery("filtered"))
            total = await session.scalar(count_stmt) or 0

            # Apply ordering
            if order_by == "label":
                stmt = stmt.order_by(AnnAlias.c.label.nullslast())
            elif order_by == "created_at":
                stmt = stmt.order_by(SampleORM.created_at.desc())
            else:
                stmt = stmt.order_by(SampleORM.id)

            # Apply pagination
            stmt = stmt.offset(offset).limit(limit)

            rows = (await session.execute(stmt)).mappings().all()

            result = []
            for row in rows:
                latest_annotation = None
                if row["ann_id"] is not None:
                    ann_created_at = row["ann_created_at"]
                    # Normalize datetime to ISO string
                    if hasattr(ann_created_at, "isoformat"):
                        ann_created_at_str = ann_created_at.isoformat()
                    else:
                        ann_created_at_str = str(ann_created_at)
                    latest_annotation = {
                        "id": row["ann_id"],
                        "label": row["ann_label"],
                        "created_by": row["ann_created_by"],
                        "created_at": ann_created_at_str,
                    }

                latest_prediction = None
                if row["pred_id"] is not None:
                    latest_prediction = {
                        "id": row["pred_id"],
                        "predicted_label": row["pred_predicted_label"],
                        "score": row["pred_score"],
                        "model_artifact_id": row["pred_model_artifact_id"],
                    }

                result.append(
                    {
                        "id": row["id"],
                        "dataset_id": row["dataset_id"],
                        "image_uris": row["image_uris"],
                        "metadata": row["metadata_json"],
                        "ls_task_id": row["ls_task_id"],
                        "latest_annotation": latest_annotation,
                        "latest_prediction": latest_prediction,
                    }
                )

            return result, total

    async def create_annotation(self, annotation: Annotation, user_id: str | None = None) -> Annotation:
        async with self.session_factory() as session:
            session.add(
                AnnotationORM(
                    id=annotation.id,
                    sample_id=annotation.sample_id,
                    label=annotation.label,
                    created_by=annotation.created_by,
                    created_at=annotation.created_at,
                    user_id=user_id,
                )
            )
            await session.commit()
        return annotation

    async def list_annotations_for_dataset(self, dataset_id: str) -> list[Annotation]:
        async with self.session_factory() as session:
            stmt = select(AnnotationORM).join(SampleORM, AnnotationORM.sample_id == SampleORM.id).where(SampleORM.dataset_id == dataset_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Annotation(id=r.id, sample_id=r.sample_id, label=r.label, created_by=r.created_by, created_at=r.created_at)
                for r in rows
            ]

    async def list_annotations_for_sample(self, sample_id: str) -> list[Annotation]:
        async with self.session_factory() as session:
            stmt = select(AnnotationORM).where(AnnotationORM.sample_id == sample_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Annotation(id=r.id, sample_id=r.sample_id, label=r.label, created_by=r.created_by, created_at=r.created_at)
                for r in rows
            ]

    async def get_annotation(self, annotation_id: str) -> Annotation | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return None
            return Annotation(id=row.id, sample_id=row.sample_id, label=row.label, created_by=row.created_by, created_at=row.created_at)

    async def update_annotation(self, annotation_id: str, label: str) -> Annotation | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return None
            row.label = label
            await session.commit()
            return Annotation(id=row.id, sample_id=row.sample_id, label=row.label, created_by=row.created_by, created_at=row.created_at)

    async def delete_annotation(self, annotation_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def create_preset(self, preset: TrainingPreset, org_id: str | None = None) -> TrainingPreset:
        org_id = org_id or preset.org_id or DEFAULT_ORG_ID
        async with self.session_factory() as session:
            session.add(
                TrainingPresetORM(
                    id=preset.id,
                    org_id=org_id,
                    name=preset.name,
                    model_spec=preset.model_spec.model_dump(mode="json"),
                    omegaconf_yaml=preset.omegaconf_yaml,
                    dataloader_ref=preset.dataloader_ref,
                )
            )
            await session.commit()
        return preset.model_copy(update={"org_id": org_id})

    async def list_presets(self, org_id: str | None = None) -> list[TrainingPreset]:
        async with self.session_factory() as session:
            stmt = select(TrainingPresetORM)
            if org_id is not None:
                stmt = stmt.where(TrainingPresetORM.org_id == org_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                TrainingPreset(
                    id=r.id,
                    org_id=r.org_id,
                    name=r.name,
                    model_spec=r.model_spec,
                    omegaconf_yaml=r.omegaconf_yaml,
                    dataloader_ref=r.dataloader_ref,
                )
                for r in rows
            ]

    async def get_preset(self, preset_id: str, org_id: str | None = None) -> TrainingPreset | None:
        async with self.session_factory() as session:
            row = await session.get(TrainingPresetORM, preset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            return TrainingPreset(
                id=row.id,
                org_id=row.org_id,
                name=row.name,
                model_spec=row.model_spec,
                omegaconf_yaml=row.omegaconf_yaml,
                dataloader_ref=row.dataloader_ref,
            )

    async def create_job(self, job: TrainingJob, org_id: str | None = None, user_id: str | None = None) -> TrainingJob:
        org_id = org_id or job.org_id or DEFAULT_ORG_ID
        async with self.session_factory() as session:
            session.add(
                TrainingJobORM(
                    id=job.id,
                    org_id=org_id,
                    dataset_id=job.dataset_id,
                    preset_id=job.preset_id,
                    status=job.status.value,
                    created_by=job.created_by,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    user_id=user_id,
                )
            )
            session.add(JobUserStateORM(job_id=job.id, user_left=False))
            await session.commit()
        return job.model_copy(update={"org_id": org_id})

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return
            row.external_job_id = external_job_id
            row.updated_at = _utcnow()
            await session.commit()

    async def update_job_status(self, job_id: str, status: JobStatus) -> None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return
            row.status = status.value
            row.updated_at = _utcnow()
            await session.commit()

    async def get_job_external_id(self, job_id: str) -> str | None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            return None if row is None else row.external_job_id

    async def list_jobs(self, org_id: str | None = None) -> list[TrainingJob]:
        async with self.session_factory() as session:
            stmt = select(TrainingJobORM).order_by(TrainingJobORM.created_at.desc())
            if org_id is not None:
                stmt = stmt.where(or_(TrainingJobORM.org_id == org_id, TrainingJobORM.is_public == True))  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            jobs: list[TrainingJob] = []
            for row in rows:
                arts = await self._list_artifacts_by_job_in_session(session, row.id)
                jobs.append(
                    TrainingJob(
                        id=row.id,
                        org_id=row.org_id,
                        dataset_id=row.dataset_id,
                        preset_id=row.preset_id,
                        status=row.status,
                        created_by=row.created_by,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        artifact_refs=arts,
                    )
                )
            return jobs

    async def get_job(self, job_id: str, org_id: str | None = None) -> TrainingJob | None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
            arts = await self._list_artifacts_by_job_in_session(session, row.id)
            return TrainingJob(
                id=row.id,
                org_id=row.org_id,
                dataset_id=row.dataset_id,
                preset_id=row.preset_id,
                status=row.status,
                created_by=row.created_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
                artifact_refs=arts,
            )

    async def add_event(self, event: TrainingEvent) -> None:
        async with self.session_factory() as session:
            session.add(
                TrainingEventORM(
                    job_id=event.job_id,
                    ts=event.ts,
                    level=event.level,
                    message=event.message,
                    payload=event.payload,
                )
            )
            await session.commit()

    async def list_events(self, job_id: str) -> list[TrainingEvent]:
        async with self.session_factory() as session:
            rows = (await session.execute(select(TrainingEventORM).where(TrainingEventORM.job_id == job_id).order_by(TrainingEventORM.id.asc()))).scalars().all()
            return [TrainingEvent(job_id=r.job_id, ts=r.ts, level=r.level, message=r.message, payload=r.payload) for r in rows]

    async def list_events_paginated(self, job_id: str, offset: int = 0, limit: int = 50) -> tuple[list[TrainingEvent], int]:
        async with self.session_factory() as session:
            total = await session.scalar(
                select(func.count()).select_from(TrainingEventORM).where(TrainingEventORM.job_id == job_id)
            )
            rows = (
                await session.execute(
                    select(TrainingEventORM)
                    .where(TrainingEventORM.job_id == job_id)
                    .order_by(TrainingEventORM.id.asc())
                    .offset(offset)
                    .limit(limit)
                )
            ).scalars().all()
            return [TrainingEvent(job_id=r.job_id, ts=r.ts, level=r.level, message=r.message, payload=r.payload) for r in rows], total or 0

    async def mark_user_left(self, job_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(JobUserStateORM, job_id)
            if row is None:
                return False
            row.user_left = True
            await session.commit()
            return True

    async def did_user_leave(self, job_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(JobUserStateORM, job_id)
            return False if row is None else row.user_left

    async def add_artifacts(self, job_id: str, artifacts: list[ArtifactRef]) -> None:
        async with self.session_factory() as session:
            for a in artifacts:
                session.add(ArtifactORM(id=a.id, job_id=job_id, uri=a.uri, kind=a.kind, metadata_json=a.metadata))
            await session.commit()

    async def get_artifact(self, artifact_id: str) -> ArtifactRef | None:
        async with self.session_factory() as session:
            row = await session.get(ArtifactORM, artifact_id)
            if row is None:
                return None
            return ArtifactRef(id=row.id, uri=row.uri, kind=row.kind, metadata=row.metadata_json)

    async def create_prediction(self, prediction: PredictionResult) -> PredictionResult:
        async with self.session_factory() as session:
            session.add(
                PredictionORM(
                    id=prediction.id,
                    result_type=prediction.result_type.value,
                    sample_id=prediction.sample_id,
                    predicted_label=prediction.predicted_label,
                    score=prediction.score,
                    model_artifact_id=prediction.model_artifact_id,
                )
            )
            await session.commit()
        return prediction

    async def list_predictions(self) -> list[PredictionResult]:
        async with self.session_factory() as session:
            rows = (await session.execute(select(PredictionORM))).scalars().all()
            return [
                PredictionResult(
                    id=r.id,
                    result_type=r.result_type,
                    sample_id=r.sample_id,
                    predicted_label=r.predicted_label,
                    score=r.score,
                    model_artifact_id=r.model_artifact_id,
                )
                for r in rows
            ]

    async def list_predictions_for_dataset(self, dataset_id: str) -> list[PredictionResult]:
        async with self.session_factory() as session:
            stmt = (
                select(PredictionORM)
                .join(SampleORM, PredictionORM.sample_id == SampleORM.id)
                .where(SampleORM.dataset_id == dataset_id)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PredictionResult(
                    id=r.id,
                    result_type=r.result_type,
                    sample_id=r.sample_id,
                    predicted_label=r.predicted_label,
                    score=r.score,
                    model_artifact_id=r.model_artifact_id,
                )
                for r in rows
            ]

    async def get_prediction(self, prediction_id: str) -> PredictionResult | None:
        async with self.session_factory() as session:
            row = await session.get(PredictionORM, prediction_id)
            if row is None:
                return None
            return PredictionResult(
                id=row.id,
                result_type=row.result_type,
                sample_id=row.sample_id,
                predicted_label=row.predicted_label,
                score=row.score,
                model_artifact_id=row.model_artifact_id,
            )

    async def create_prediction_edit(self, edit: PredictionEdit, user_id: str | None = None) -> PredictionEdit:
        async with self.session_factory() as session:
            session.add(
                PredictionEditORM(
                    id=edit.id,
                    result_id=edit.result_id,
                    corrected_label=edit.corrected_label,
                    edited_by=edit.edited_by,
                    edited_at=edit.edited_at,
                    user_id=user_id,
                )
            )
            await session.commit()
        return edit

    async def update_sample_image_uris(self, sample_id: str, image_uris: list[str]) -> Sample | None:
        async with self.session_factory() as session:
            row = await session.get(SampleORM, sample_id)
            if row is None:
                return None
            row.image_uris = image_uris
            await session.commit()
            return Sample(
                id=row.id,
                dataset_id=row.dataset_id,
                image_uris=row.image_uris,
                metadata=row.metadata_json,
                ls_task_id=row.ls_task_id,
            )

    async def update_sample_ls_task_id(self, sample_id: str, ls_task_id: int) -> None:
        async with self.session_factory() as session:
            row = await session.get(SampleORM, sample_id)
            if row is not None:
                row.ls_task_id = ls_task_id
                await session.commit()

    async def _list_artifacts_by_job_in_session(self, session: AsyncSession, job_id: str) -> list[ArtifactRef]:
        rows = (await session.execute(select(ArtifactORM).where(ArtifactORM.job_id == job_id))).scalars().all()
        return [ArtifactRef(id=r.id, uri=r.uri, kind=r.kind, metadata=r.metadata_json) for r in rows]

    async def upsert_sample_feature(
        self,
        sample_id: str,
        embedding: list[float],
        embed_model: str,
    ) -> SampleFeature:
        now = _utcnow()
        async with self.session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                row = SampleFeatureORM(
                    sample_id=sample_id,
                    embedding=embedding,
                    embed_model=embed_model,
                    computed_at=now,
                )
                session.add(row)
            else:
                row.embedding = embedding
                row.embed_model = embed_model
                row.computed_at = now
            await session.commit()

            # Update pgvector column via raw SQL (Postgres only)
            try:
                dialect_name = session.bind.dialect.name  # type: ignore[union-attr]
            except Exception:
                dialect_name = ""
            if dialect_name == "postgresql":
                vec_str = str(embedding)  # "[0.1, 0.2, ...]"
                await session.execute(
                    text(
                        "UPDATE sample_features SET embedding_vec = :vec::vector WHERE sample_id = :sid"
                    ),
                    {"vec": vec_str, "sid": sample_id},
                )
                await session.commit()

        return SampleFeature(
            sample_id=sample_id,
            embedding=embedding,
            embed_model=embed_model,
            computed_at=now,
        )

    async def get_sample_feature(self, sample_id: str) -> SampleFeature | None:
        async with self.session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                return None
            return SampleFeature(
                sample_id=row.sample_id,
                embedding=row.embedding,
                embed_model=row.embed_model,
                computed_at=row.computed_at,
            )

    async def similarity_search(
        self,
        embedding: list[float],
        dataset_id: str,
        k: int,
        exclude_id: str = "",
    ) -> list[dict]:
        """Find k nearest samples in dataset by cosine similarity.

        Uses pgvector <=> operator on Postgres, falls back to Python cosine on SQLite.
        Returns list of {"sample_id": str, "score": float} sorted by score desc.
        """
        async with self.session_factory() as session:
            # Detect dialect
            try:
                dialect = session.bind.dialect.name  # type: ignore[union-attr]
            except Exception:
                dialect = "sqlite"

            if dialect == "postgresql":
                # pgvector cosine distance — lower is more similar
                vec_str = str(embedding)
                sql = text("""
                    SELECT sf.sample_id,
                           1 - (sf.embedding_vec <=> :vec::vector) AS score
                    FROM sample_features sf
                    JOIN samples s ON s.id = sf.sample_id
                    WHERE s.dataset_id = :did
                      AND sf.sample_id != :exclude
                      AND sf.embedding_vec IS NOT NULL
                    ORDER BY sf.embedding_vec <=> :vec::vector
                    LIMIT :k
                """)
                rows = (await session.execute(sql, {
                    "vec": vec_str,
                    "did": dataset_id,
                    "exclude": exclude_id,
                    "k": k,
                })).fetchall()
                return [{"sample_id": row[0], "score": float(row[1])} for row in rows]

            else:
                # SQLite fallback: Python cosine similarity over JSON embeddings
                # Get all features for samples in this dataset
                sql = text("""
                    SELECT sf.sample_id, sf.embedding
                    FROM sample_features sf
                    JOIN samples s ON s.id = sf.sample_id
                    WHERE s.dataset_id = :did
                      AND sf.sample_id != :exclude
                """)
                rows = (await session.execute(sql, {
                    "did": dataset_id,
                    "exclude": exclude_id,
                })).fetchall()

                if not rows:
                    return []

                import math

                def cosine(a: list[float], b: list[float]) -> float:
                    dot = sum(x * y for x, y in zip(a, b))
                    na = math.sqrt(sum(x * x for x in a))
                    nb = math.sqrt(sum(x * x for x in b))
                    if na == 0 or nb == 0:
                        return 0.0
                    return dot / (na * nb)

                results = []
                for row in rows:
                    candidate_embedding = row[1]  # JSON column — may be str on SQLite
                    if not candidate_embedding:
                        continue
                    if isinstance(candidate_embedding, str):
                        candidate_embedding = json.loads(candidate_embedding)
                    score = cosine(embedding, candidate_embedding)
                    results.append({"sample_id": row[0], "score": score})

                # Sort by score descending, take top k
                results.sort(key=lambda x: x["score"], reverse=True)
                return results[:k]

    async def list_model_assets(self, dataset_id: str, org_id: str | None = None) -> list[ArtifactRef]:
        """Return artifact refs for all training jobs on dataset_id, optionally filtered by org_id."""
        async with self.session_factory() as session:
            stmt = (
                select(ArtifactORM)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .where(TrainingJobORM.dataset_id == dataset_id)
            )
            if org_id is not None:
                stmt = stmt.where(or_(TrainingJobORM.org_id == org_id, TrainingJobORM.is_public == True))  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            return [ArtifactRef(id=r.id, uri=r.uri, kind=r.kind, metadata=r.metadata_json) for r in rows]

    # ------------------------------------------------------------------
    # Schedule CRUD
    # ------------------------------------------------------------------

    async def create_schedule(self, schedule: ScheduleORM) -> ScheduleORM:
        async with self.session_factory() as session:
            session.add(schedule)
            await session.flush()
            await session.refresh(schedule)
            # Detach from session so the object can be used outside
            session.expunge(schedule)
            await session.commit()
            return schedule

    async def list_schedules(self, org_id: str) -> list[ScheduleORM]:
        async with self.session_factory() as session:
            stmt = (
                select(ScheduleORM)
                .where(ScheduleORM.org_id == org_id)
                .order_by(ScheduleORM.created_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            # Expunge so callers can use them outside session
            for row in rows:
                session.expunge(row)
            return list(rows)

    async def get_schedule(self, schedule_id: str, org_id: str | None = None) -> ScheduleORM | None:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            session.expunge(row)
            return row

    async def update_schedule(self, schedule_id: str, **kwargs: object) -> ScheduleORM | None:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None:
                return None
            for key, value in kwargs.items():
                setattr(row, key, value)
            row.updated_at = _utcnow()
            await session.flush()
            await session.refresh(row)
            session.expunge(row)
            await session.commit()
            return row

    async def delete_schedule(self, schedule_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ScheduleORM, schedule_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # User / Auth CRUD
    # ------------------------------------------------------------------

    async def get_user_by_email(self, email: str) -> UserORM | None:
        async with self.session_factory() as session:
            result = await session.execute(select(UserORM).where(UserORM.email == email))
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def get_user(self, user_id: str) -> UserORM | None:
        async with self.session_factory() as session:
            row = await session.get(UserORM, user_id)
            if row is not None:
                session.expunge(row)
            return row

    async def create_user(self, user: UserORM) -> UserORM:
        async with self.session_factory() as session:
            session.add(user)
            await session.flush()
            await session.refresh(user)
            session.expunge(user)
            await session.commit()
            return user

    # ------------------------------------------------------------------
    # PAT CRUD
    # ------------------------------------------------------------------

    async def create_pat(self, pat: PersonalAccessTokenORM) -> PersonalAccessTokenORM:
        async with self.session_factory() as session:
            session.add(pat)
            await session.flush()
            await session.refresh(pat)
            session.expunge(pat)
            await session.commit()
            return pat

    async def list_personal_access_tokens(self, user_id: str) -> list[PersonalAccessTokenORM]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(PersonalAccessTokenORM)
                .where(PersonalAccessTokenORM.user_id == user_id)
                .order_by(PersonalAccessTokenORM.created_at.desc())
            )
            rows = result.scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    async def delete_personal_access_token(self, token_id: str, user_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(PersonalAccessTokenORM, token_id)
            if row is None or row.user_id != user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Organization CRUD
    # ------------------------------------------------------------------

    async def create_organization(self, org: OrganizationORM) -> OrganizationORM:
        async with self.session_factory() as session:
            session.add(org)
            await session.flush()
            await session.refresh(org)
            session.expunge(org)
            await session.commit()
            return org

    async def get_organization(self, org_id: str) -> OrganizationORM | None:
        async with self.session_factory() as session:
            row = await session.get(OrganizationORM, org_id)
            if row is not None:
                session.expunge(row)
            return row

    async def get_organization_by_slug(self, slug: str) -> OrganizationORM | None:
        async with self.session_factory() as session:
            result = await session.execute(select(OrganizationORM).where(OrganizationORM.slug == slug))
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def list_all_organizations(self) -> list[OrganizationORM]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrganizationORM).order_by(OrganizationORM.created_at.desc())
            )
            rows = result.scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    # ------------------------------------------------------------------
    # Org Membership CRUD
    # ------------------------------------------------------------------

    async def add_org_member(self, membership: OrgMembershipORM) -> OrgMembershipORM:
        async with self.session_factory() as session:
            session.add(membership)
            await session.flush()
            await session.refresh(membership)
            session.expunge(membership)
            await session.commit()
            return membership

    async def get_org_members(self, org_id: str) -> list[tuple[OrgMembershipORM, UserORM]]:
        """Return list of (membership, user) tuples for org."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM, UserORM)
                .join(UserORM, OrgMembershipORM.user_id == UserORM.id)
                .where(OrgMembershipORM.org_id == org_id)
                .order_by(OrgMembershipORM.created_at.asc())
            )
            rows = result.all()
            out = []
            for membership, user in rows:
                session.expunge(membership)
                session.expunge(user)
                out.append((membership, user))
            return out

    async def get_org_membership(self, org_id: str, user_id: str) -> OrgMembershipORM | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM).where(
                    OrgMembershipORM.org_id == org_id,
                    OrgMembershipORM.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def remove_org_member(self, org_id: str, user_id: str) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM).where(
                    OrgMembershipORM.org_id == org_id,
                    OrgMembershipORM.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def get_user_orgs(self, user_id: str) -> list[tuple[OrgMembershipORM, OrganizationORM]]:
        """Return list of (membership, org) tuples for user."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM, OrganizationORM)
                .join(OrganizationORM, OrgMembershipORM.org_id == OrganizationORM.id)
                .where(OrgMembershipORM.user_id == user_id)
                .order_by(OrgMembershipORM.created_at.asc())
            )
            rows = result.all()
            out = []
            for membership, org in rows:
                session.expunge(membership)
                session.expunge(org)
                out.append((membership, org))
            return out
