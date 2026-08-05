from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.api.schemas import ArtifactRef, Model
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM
from app.shared.db.models.dataset_collections import DatasetCollectionORM
from app.shared.db.models.training import TrainingJobORM
from app.shared.db.models.auth import UserORM


def _assert_str(value: str | None) -> str:
    assert value is not None
    return value


def _creator_name(
    created_by: str, user_name: str | None, user_email: str | None
) -> str:
    if created_by == "system":
        return "system"
    return str(user_name or user_email or created_by)


class ModelArtifactRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
    ) -> list[Model]:
        models, _ = await self.list_models_paginated(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            offset=0,
            limit=None,
        )
        return models

    async def list_models_paginated(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        *,
        offset: int = 0,
        limit: int | None = 50,
    ) -> tuple[list[Model], int]:
        async with self.session_factory() as session:
            conditions = [
                ArtifactORM.kind == "model",
                or_(
                    TrainingJobORM.org_id == org_id,
                    TrainingJobORM.is_public.is_(True),
                ),
            ]
            if dataset_id is not None:
                conditions.append(TrainingJobORM.dataset_id == dataset_id)
            if job_id is not None:
                conditions.append(ArtifactORM.job_id == job_id)

            joins = (
                select(ArtifactORM.id)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .where(*conditions)
            )
            total = int(
                await session.scalar(select(func.count()).select_from(joins.subquery()))
                or 0
            )
            stmt = (
                select(
                    ArtifactORM,
                    TrainingJobORM,
                    DatasetORM,
                    DatasetCollectionORM,
                    UserORM.name,
                    UserORM.email,
                )
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .outerjoin(
                    DatasetCollectionORM,
                    TrainingJobORM.collection_id == DatasetCollectionORM.id,
                )
                .outerjoin(UserORM, UserORM.id == TrainingJobORM.created_by)
                .where(*conditions)
                .order_by(
                    ArtifactORM.created_at.desc().nulls_last(),
                    ArtifactORM.id.desc(),
                )
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)

            rows = (await session.execute(stmt)).all()
            return [
                Model(
                    id=artifact.id,
                    uri=artifact.uri,
                    kind=artifact.kind,
                    metadata=artifact.metadata_json,
                    name=artifact.name,
                    file_size=artifact.file_size,
                    file_hash=artifact.file_hash,
                    format=artifact.format,
                    created_at=artifact.created_at,
                    job_id=_assert_str(artifact.job_id),
                    dataset_id=job.dataset_id,
                    dataset_name=dataset.name if dataset is not None else None,
                    collection_id=job.collection_id,
                    collection_revision_id=job.collection_revision_id,
                    collection_name=(
                        collection.name if collection is not None else None
                    ),
                    trainer_id=job.trainer_id,
                    trainer_name=job.trainer_id,
                    created_by=job.created_by,
                    creator_name=_creator_name(job.created_by, user_name, user_email),
                )
                for artifact, job, dataset, collection, user_name, user_email in rows
            ], total

    async def get_model(
        self,
        artifact_id: str,
        org_id: str,
        *,
        include_public: bool = True,
    ) -> Model | None:
        async with self.session_factory() as session:
            access_filter = TrainingJobORM.org_id == org_id
            if include_public:
                access_filter = or_(
                    TrainingJobORM.org_id == org_id,
                    TrainingJobORM.is_public.is_(True),
                )  # noqa: E712
            stmt = (
                select(
                    ArtifactORM,
                    TrainingJobORM,
                    DatasetORM,
                    DatasetCollectionORM,
                    UserORM.name,
                    UserORM.email,
                )
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .outerjoin(
                    DatasetCollectionORM,
                    TrainingJobORM.collection_id == DatasetCollectionORM.id,
                )
                .outerjoin(UserORM, UserORM.id == TrainingJobORM.created_by)
                .where(ArtifactORM.id == artifact_id)
                .where(ArtifactORM.kind == "model")
                .where(access_filter)
            )
            row = (await session.execute(stmt)).first()
            if row is None:
                return None
            artifact, job, dataset, collection, user_name, user_email = row
            return Model(
                id=artifact.id,
                uri=artifact.uri,
                kind=artifact.kind,
                metadata=artifact.metadata_json,
                name=artifact.name,
                file_size=artifact.file_size,
                file_hash=artifact.file_hash,
                format=artifact.format,
                created_at=artifact.created_at,
                job_id=_assert_str(artifact.job_id),
                dataset_id=job.dataset_id,
                dataset_name=dataset.name if dataset is not None else None,
                collection_id=job.collection_id,
                collection_revision_id=job.collection_revision_id,
                collection_name=collection.name if collection is not None else None,
                trainer_id=job.trainer_id,
                trainer_name=job.trainer_id,
                created_by=job.created_by,
                creator_name=_creator_name(job.created_by, user_name, user_email),
            )

    async def rename_model(
        self, artifact_id: str, org_id: str, name: str
    ) -> Model | None:
        async with self.session_factory() as session:
            stmt = (
                select(
                    ArtifactORM,
                    TrainingJobORM,
                    DatasetORM,
                    DatasetCollectionORM,
                    UserORM.name,
                    UserORM.email,
                )
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .outerjoin(
                    DatasetCollectionORM,
                    TrainingJobORM.collection_id == DatasetCollectionORM.id,
                )
                .outerjoin(UserORM, UserORM.id == TrainingJobORM.created_by)
                .where(ArtifactORM.id == artifact_id)
                .where(ArtifactORM.kind == "model")
                .where(TrainingJobORM.org_id == org_id)
            )
            row = (await session.execute(stmt)).first()
            if row is None:
                return None
            artifact, job, dataset, collection, user_name, user_email = row
            artifact.name = name
            await session.commit()
            return Model(
                id=artifact.id,
                uri=artifact.uri,
                kind=artifact.kind,
                metadata=artifact.metadata_json,
                name=artifact.name,
                file_size=artifact.file_size,
                file_hash=artifact.file_hash,
                format=artifact.format,
                created_at=artifact.created_at,
                job_id=_assert_str(artifact.job_id),
                dataset_id=job.dataset_id,
                dataset_name=dataset.name if dataset is not None else None,
                collection_id=job.collection_id,
                collection_revision_id=job.collection_revision_id,
                collection_name=collection.name if collection is not None else None,
                trainer_id=job.trainer_id,
                trainer_name=job.trainer_id,
                created_by=job.created_by,
                creator_name=_creator_name(job.created_by, user_name, user_email),
            )

    async def delete_artifact(self, artifact_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ArtifactORM, artifact_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_artifact_uris_by_job(self, job_id: str) -> list[tuple[str, str]]:
        async with self.session_factory() as session:
            stmt = select(ArtifactORM.id, ArtifactORM.uri).where(
                ArtifactORM.job_id == job_id
            )
            rows = (await session.execute(stmt)).all()
            return [(row.id, row.uri) for row in rows]

    async def delete_artifacts_by_ids(self, artifact_ids: list[str]) -> None:
        if not artifact_ids:
            return
        async with self.session_factory() as session:
            await session.execute(
                delete(ArtifactORM).where(ArtifactORM.id.in_(artifact_ids))
            )
            await session.commit()

    async def add_artifacts(self, job_id: str, artifacts: list[ArtifactRef]) -> None:
        async with self.session_factory() as session:
            for a in artifacts:
                session.add(
                    ArtifactORM(
                        id=a.id,
                        job_id=job_id,
                        uri=a.uri,
                        kind=a.kind,
                        metadata_json=a.metadata,
                        name=a.name,
                        file_size=a.file_size,
                        file_hash=a.file_hash,
                        format=a.format,
                        created_at=a.created_at,
                    )
                )
            await session.commit()

    async def list_model_assets(
        self, dataset_id: str, org_id: str | None = None
    ) -> list[ArtifactRef]:
        async with self.session_factory() as session:
            stmt = (
                select(ArtifactORM)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .where(TrainingJobORM.dataset_id == dataset_id)
            )
            if org_id is not None:
                stmt = stmt.where(
                    or_(
                        TrainingJobORM.org_id == org_id,
                        TrainingJobORM.is_public.is_(True),
                    )
                )  # noqa: E712
            rows = (await session.execute(stmt)).scalars().all()
            return [
                ArtifactRef(id=r.id, uri=r.uri, kind=r.kind, metadata=r.metadata_json)
                for r in rows
            ]
