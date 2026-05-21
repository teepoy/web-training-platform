from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db.registry import (
    AnnotationORM,
    AnnotationVersionORM,
    ArtifactORM,
    DatasetORM,
    OrganizationORM,
    PlatformPredictionORM,
    PredictionCollectionItemORM,
    PredictionCollectionORM,
    PredictionEventORM,
    PredictionJobORM,
    PredictionReviewActionORM,
    SampleFeatureORM,
    SampleORM,
)
from app.shared.api.schemas import (
    Annotation,
    Dataset,
    DEFAULT_ORG_ID,
    Sample,
    SampleFeature,
    TaskSpec,
)
from app.shared.api.schemas import DatasetStorageMode, DatasetType
from app.shared.db.models.training import (
    JobUserStateORM,
    TrainingEventORM,
    TrainingJobORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _org_name_for(session: AsyncSession, org_id: str | None) -> str:
    if not org_id:
        return ""
    org_row = await session.get(OrganizationORM, org_id)
    return "" if org_row is None else org_row.name


class DatasetRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_dataset(
        self, dataset: Dataset, org_id: str | None = None
    ) -> Dataset:
        org_id = org_id or dataset.org_id or DEFAULT_ORG_ID
        async with self.session_factory() as session:
            org_name = await _org_name_for(session, org_id)
            row = DatasetORM(
                id=dataset.id,
                org_id=org_id,
                name=dataset.name,
                dataset_type=dataset.dataset_type.value,
                task_spec=dataset.task_spec.model_dump(mode="json"),
                is_public=dataset.is_public,
                created_at=dataset.created_at,
                embed_config=dataset.embed_config or None,
                ls_project_id=dataset.ls_project_id,
                storage_mode=dataset.storage_mode.value,
            )
            session.add(row)
            await session.commit()
        return dataset.model_copy(update={"org_id": org_id, "org_name": org_name})

    async def list_datasets(self, org_id: str | None = None) -> list[Dataset]:
        async with self.session_factory() as session:
            stmt = select(DatasetORM).order_by(DatasetORM.created_at.desc())
            if org_id is not None:
                stmt = stmt.where(
                    or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True))
                )  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Dataset(
                    id=r.id,
                    org_id=r.org_id,
                    org_name=await _org_name_for(session, r.org_id),
                    name=r.name,
                    dataset_type=cast(DatasetType, r.dataset_type),
                    task_spec=cast(TaskSpec, r.task_spec),
                    is_public=r.is_public,
                    created_at=r.created_at,
                    embed_config=r.embed_config or {},
                    ls_project_id=r.ls_project_id,
                    storage_mode=cast(DatasetStorageMode, r.storage_mode),
                )
                for r in rows
            ]

    async def get_dataset(
        self, dataset_id: str, org_id: str | None = None
    ) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
            return Dataset(
                id=row.id,
                org_id=row.org_id,
                org_name=await _org_name_for(session, row.org_id),
                name=row.name,
                dataset_type=cast(DatasetType, row.dataset_type),
                task_spec=cast(TaskSpec, row.task_spec),
                is_public=row.is_public,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
                storage_mode=cast(DatasetStorageMode, row.storage_mode),
            )

    async def update_dataset_embed_config(
        self, dataset_id: str, embed_config: dict
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is not None:
                row.embed_config = embed_config
                await session.commit()

    async def delete_dataset(self, dataset_id: str, org_id: str | None = None) -> bool:
        async with self.session_factory() as session:
            dataset = await session.get(DatasetORM, dataset_id)
            if dataset is None:
                return False
            if org_id is not None and dataset.org_id != org_id:
                return False

            training_job_ids = select(TrainingJobORM.id).where(
                TrainingJobORM.dataset_id == dataset_id
            )
            prediction_job_ids = select(PredictionJobORM.id).where(
                PredictionJobORM.dataset_id == dataset_id
            )
            sample_ids = select(SampleORM.id).where(SampleORM.dataset_id == dataset_id)
            annotation_ids = select(AnnotationORM.id).where(
                AnnotationORM.sample_id.in_(sample_ids)
            )
            prediction_ids = select(PlatformPredictionORM.id).where(
                PlatformPredictionORM.dataset_id == dataset_id
            )
            collection_ids = select(PredictionCollectionORM.id).where(
                PredictionCollectionORM.dataset_id == dataset_id
            )
            review_action_ids = select(PredictionReviewActionORM.id).where(
                PredictionReviewActionORM.dataset_id == dataset_id
            )

            await session.execute(
                delete(TrainingEventORM).where(
                    TrainingEventORM.job_id.in_(training_job_ids)
                )
            )
            await session.execute(
                delete(JobUserStateORM).where(
                    JobUserStateORM.job_id.in_(training_job_ids)
                )
            )
            await session.execute(
                delete(ArtifactORM).where(ArtifactORM.job_id.in_(training_job_ids))
            )
            await session.execute(
                delete(PredictionEventORM).where(
                    PredictionEventORM.job_id.in_(prediction_job_ids)
                )
            )
            await session.execute(
                delete(PredictionCollectionItemORM).where(
                    PredictionCollectionItemORM.collection_id.in_(collection_ids)
                )
            )
            await session.execute(
                delete(AnnotationVersionORM).where(
                    AnnotationVersionORM.annotation_id.in_(annotation_ids)
                )
            )
            await session.execute(
                delete(PredictionReviewActionORM).where(
                    PredictionReviewActionORM.id.in_(review_action_ids)
                )
            )
            await session.execute(
                delete(PredictionCollectionORM).where(
                    PredictionCollectionORM.id.in_(collection_ids)
                )
            )
            await session.execute(
                delete(PlatformPredictionORM).where(
                    PlatformPredictionORM.id.in_(prediction_ids)
                )
            )
            await session.execute(
                delete(PredictionJobORM).where(
                    PredictionJobORM.dataset_id == dataset_id
                )
            )
            await session.execute(
                delete(TrainingJobORM).where(TrainingJobORM.dataset_id == dataset_id)
            )
            await session.execute(
                delete(SampleFeatureORM).where(
                    SampleFeatureORM.sample_id.in_(sample_ids)
                )
            )
            await session.execute(
                delete(AnnotationORM).where(AnnotationORM.sample_id.in_(sample_ids))
            )
            await session.execute(
                delete(SampleORM).where(SampleORM.dataset_id == dataset_id)
            )
            await session.execute(
                delete(PredictionReviewActionORM).where(
                    PredictionReviewActionORM.dataset_id == dataset_id
                )
            )
            await session.delete(dataset)
            await session.commit()
            return True

    async def update_dataset_task_spec(
        self, dataset_id: str, task_spec: dict
    ) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            row.task_spec = task_spec
            await session.commit()
            return Dataset(
                id=row.id,
                org_id=row.org_id,
                org_name=await _org_name_for(session, row.org_id),
                name=row.name,
                dataset_type=cast(DatasetType, row.dataset_type),
                task_spec=cast(TaskSpec, row.task_spec),
                is_public=row.is_public,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
                storage_mode=cast(DatasetStorageMode, row.storage_mode),
            )

    async def set_dataset_public(self, dataset_id: str, is_public: bool) -> bool:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return False
            row.is_public = is_public
            await session.commit()
            return True


class SampleRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

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

    async def create_samples(self, samples: list[Sample]) -> list[Sample]:
        if not samples:
            return []
        async with self.session_factory() as session:
            session.add_all(
                [
                    SampleORM(
                        id=sample.id,
                        dataset_id=sample.dataset_id,
                        image_uris=sample.image_uris,
                        metadata_json=sample.metadata,
                        ls_task_id=sample.ls_task_id,
                    )
                    for sample in samples
                ]
            )
            await session.commit()
        return samples

    async def list_samples(
        self, dataset_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[Sample], int]:
        async with self.session_factory() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(SampleORM)
                .where(SampleORM.dataset_id == dataset_id)
            )
            rows = (
                (
                    await session.execute(
                        select(SampleORM)
                        .where(SampleORM.dataset_id == dataset_id)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
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

    async def list_wafer_points(self, dataset_id: str) -> list[dict[str, object]]:
        async with self.session_factory() as session:
            rows = await session.execute(
                select(SampleORM.id, SampleORM.metadata_json).where(
                    SampleORM.dataset_id == dataset_id
                )
            )

            points: list[dict[str, object]] = []
            for sample_id, metadata_json in rows.all():
                metadata = metadata_json if isinstance(metadata_json, dict) else {}
                wafer_x = metadata.get("wafer_x")
                wafer_y = metadata.get("wafer_y")
                if wafer_x is None or wafer_y is None:
                    continue
                try:
                    x = float(wafer_x)
                    y = float(wafer_y)
                except (TypeError, ValueError):
                    continue
                points.append({"id": sample_id, "x": x, "y": y})

            return points

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
        sample_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        from sqlalchemy import alias, and_

        if sample_ids is not None and len(sample_ids) == 0:
            return [], 0

        async with self.session_factory() as session:
            latest_ann_subq = (
                select(
                    AnnotationORM.sample_id.label("sample_id"),
                    func.max(AnnotationORM.created_at).label("max_created_at"),
                )
                .group_by(AnnotationORM.sample_id)
                .subquery("latest_ann_time")
            )
            ann_alias = alias(AnnotationORM.__table__, name="ann")
            stmt = (
                select(
                    SampleORM.id,
                    SampleORM.dataset_id,
                    SampleORM.image_uris,
                    SampleORM.metadata_json,
                    SampleORM.ls_task_id,
                    ann_alias.c.id.label("ann_id"),
                    ann_alias.c.label.label("ann_label"),
                    ann_alias.c.created_by.label("ann_created_by"),
                    ann_alias.c.created_at.label("ann_created_at"),
                )
                .where(SampleORM.dataset_id == dataset_id)
                .outerjoin(latest_ann_subq, latest_ann_subq.c.sample_id == SampleORM.id)
                .outerjoin(
                    ann_alias,
                    and_(
                        ann_alias.c.sample_id == SampleORM.id,
                        ann_alias.c.created_at == latest_ann_subq.c.max_created_at,
                    ),
                )
            )
            if label_filter == "__unlabeled__":
                stmt = stmt.where(ann_alias.c.id.is_(None))
            elif label_filter is not None:
                stmt = stmt.where(ann_alias.c.label == label_filter)
            if sample_ids is not None:
                stmt = stmt.where(SampleORM.id.in_(sample_ids))
            total = (
                await session.scalar(
                    select(func.count()).select_from(stmt.subquery("filtered"))
                )
                or 0
            )
            if order_by == "label":
                stmt = stmt.order_by(ann_alias.c.label.nullslast())
            elif order_by == "created_at":
                stmt = stmt.order_by(SampleORM.created_at.desc())
            else:
                stmt = stmt.order_by(SampleORM.id)
            rows = (
                (await session.execute(stmt.offset(offset).limit(limit)))
                .mappings()
                .all()
            )

            result = []
            for row in rows:
                latest_annotation = None
                if row["ann_id"] is not None:
                    ann_created_at = row["ann_created_at"]
                    latest_annotation = {
                        "id": row["ann_id"],
                        "label": row["ann_label"],
                        "created_by": row["ann_created_by"],
                        "created_at": ann_created_at.isoformat()
                        if hasattr(ann_created_at, "isoformat")
                        else str(ann_created_at),
                    }
                result.append(
                    {
                        "id": row["id"],
                        "dataset_id": row["dataset_id"],
                        "image_uris": row["image_uris"],
                        "metadata": row["metadata_json"],
                        "ls_task_id": row["ls_task_id"],
                        "latest_annotation": latest_annotation,
                    }
                )
            return result, total

    async def get_annotation_stats(self, dataset_id: str) -> dict:
        from sqlalchemy import alias, and_

        async with self.session_factory() as session:
            latest_ann_subq = (
                select(
                    AnnotationORM.sample_id.label("sample_id"),
                    func.max(AnnotationORM.created_at).label("max_created_at"),
                )
                .group_by(AnnotationORM.sample_id)
                .subquery("latest_ann_time")
            )
            ann_alias = alias(AnnotationORM.__table__, name="ann_stats")
            base = (
                select(
                    SampleORM.id.label("sample_id"),
                    ann_alias.c.label.label("ann_label"),
                )
                .where(SampleORM.dataset_id == dataset_id)
                .outerjoin(latest_ann_subq, latest_ann_subq.c.sample_id == SampleORM.id)
                .outerjoin(
                    ann_alias,
                    and_(
                        ann_alias.c.sample_id == SampleORM.id,
                        ann_alias.c.created_at == latest_ann_subq.c.max_created_at,
                    ),
                )
                .subquery("base_stats")
            )
            total_samples = (
                await session.scalar(select(func.count()).select_from(base)) or 0
            )
            annotated_samples = (
                await session.scalar(
                    select(func.count()).select_from(
                        select(base.c.sample_id)
                        .where(base.c.ann_label.isnot(None))
                        .subquery()
                    )
                )
                or 0
            )
            label_rows = (
                await session.execute(
                    select(base.c.ann_label, func.count().label("cnt"))
                    .where(base.c.ann_label.isnot(None))
                    .group_by(base.c.ann_label)
                )
            ).all()
            return {
                "total_samples": total_samples,
                "annotated_samples": annotated_samples,
                "unlabeled_samples": total_samples - annotated_samples,
                "label_counts": {row[0]: row[1] for row in label_rows},
            }

    async def update_sample_image_uris(
        self, sample_id: str, image_uris: list[str]
    ) -> Sample | None:
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


class AnnotationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_annotation(
        self, annotation: Annotation, user_id: str | None = None
    ) -> Annotation:
        async with self.session_factory() as session:
            session.add(
                AnnotationORM(
                    id=annotation.id,
                    sample_id=annotation.sample_id,
                    label=annotation.label,
                    annotation_value=annotation.annotation_value,
                    created_by=annotation.created_by,
                    created_at=annotation.created_at,
                    user_id=user_id,
                )
            )
            await session.commit()
        return annotation

    async def list_annotations_for_dataset(self, dataset_id: str) -> list[Annotation]:
        async with self.session_factory() as session:
            stmt = (
                select(AnnotationORM)
                .join(SampleORM, AnnotationORM.sample_id == SampleORM.id)
                .where(SampleORM.dataset_id == dataset_id)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def list_annotations_for_sample(self, sample_id: str) -> list[Annotation]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AnnotationORM).where(
                            AnnotationORM.sample_id == sample_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [self._to_domain(r) for r in rows]

    async def get_annotation(self, annotation_id: str) -> Annotation | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            return None if row is None else self._to_domain(row)

    async def update_annotation(
        self, annotation_id: str, label: str
    ) -> Annotation | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return None
            row.label = label
            await session.commit()
            return self._to_domain(row)

    async def delete_annotation(self, annotation_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    @staticmethod
    def _to_domain(row: AnnotationORM) -> Annotation:
        return Annotation(
            id=row.id,
            sample_id=row.sample_id,
            label=row.label,
            annotation_value=row.annotation_value,
            created_by=row.created_by,
            created_at=row.created_at,
        )


class SampleFeatureRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

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
            try:
                dialect_name = session.bind.dialect.name  # type: ignore[union-attr]
            except Exception:
                dialect_name = ""
            if dialect_name == "postgresql":
                vec_str = str(embedding)
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
        async with self.session_factory() as session:
            try:
                dialect = session.bind.dialect.name  # type: ignore[union-attr]
            except Exception:
                dialect = "sqlite"
            if dialect == "postgresql":
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
                rows = (
                    await session.execute(
                        sql,
                        {
                            "vec": vec_str,
                            "did": dataset_id,
                            "exclude": exclude_id,
                            "k": k,
                        },
                    )
                ).fetchall()
                return [{"sample_id": row[0], "score": float(row[1])} for row in rows]

            sql = text("""
                SELECT sf.sample_id, sf.embedding
                FROM sample_features sf
                JOIN samples s ON s.id = sf.sample_id
                WHERE s.dataset_id = :did
                  AND sf.sample_id != :exclude
            """)
            rows = (
                await session.execute(sql, {"did": dataset_id, "exclude": exclude_id})
            ).fetchall()
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
                candidate_embedding = row[1]
                if not candidate_embedding:
                    continue
                if isinstance(candidate_embedding, str):
                    candidate_embedding = json.loads(candidate_embedding)
                score = cosine(embedding, candidate_embedding)
                results.append({"sample_id": row[0], "score": score})
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:k]
