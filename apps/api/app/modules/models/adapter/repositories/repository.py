from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.api.schemas import ArtifactRef, Model
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM
from app.shared.db.models.training import TrainingJobORM


class ModelArtifactRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
    ) -> list[Model]:
        async with self.session_factory() as session:
            stmt = (
                select(ArtifactORM, TrainingJobORM, DatasetORM)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .join(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .where(ArtifactORM.kind == "model")
                .where(
                    or_(
                        TrainingJobORM.org_id == org_id,
                        TrainingJobORM.is_public.is_(True),
                    )
                )  # noqa: E712
            )
            if dataset_id is not None:
                stmt = stmt.where(TrainingJobORM.dataset_id == dataset_id)
            if job_id is not None:
                stmt = stmt.where(ArtifactORM.job_id == job_id)
            stmt = stmt.order_by(ArtifactORM.created_at.desc().nulls_last())

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
                    job_id=artifact.job_id,
                    dataset_id=job.dataset_id,
                    dataset_name=dataset.name,
                    trainer_id=job.trainer_id,
                    trainer_name=job.trainer_id,
                )
                for artifact, job, dataset in rows
            ]

    async def get_model(self, artifact_id: str, org_id: str) -> Model | None:
        async with self.session_factory() as session:
            stmt = (
                select(ArtifactORM, TrainingJobORM, DatasetORM)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .join(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .where(ArtifactORM.id == artifact_id)
                .where(ArtifactORM.kind == "model")
                .where(
                    or_(
                        TrainingJobORM.org_id == org_id,
                        TrainingJobORM.is_public.is_(True),
                    )
                )  # noqa: E712
            )
            row = (await session.execute(stmt)).first()
            if row is None:
                return None
            artifact, job, dataset = row
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
                job_id=artifact.job_id,
                dataset_id=job.dataset_id,
                dataset_name=dataset.name,
                trainer_id=job.trainer_id,
                trainer_name=job.trainer_id,
            )

    async def delete_artifact(self, artifact_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ArtifactORM, artifact_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

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
