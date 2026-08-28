from __future__ import annotations

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.shared.api.schemas import ArtifactRef, CreatorSummary, Model
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.datasets import DatasetORM
from app.shared.db.models.dataset_collections import DatasetCollectionORM
from app.shared.db.models.training import TrainingJobORM
from app.shared.db.models.auth import UserORM
from app.modules.models.domain.repository import (
    CompatibleModelSpec,
    ModelSortField,
    ModelSourceType,
    SortDirection,
)


def _assert_str(value: str | None) -> str:
    assert value is not None
    return value


def _creator_name(
    created_by: str, user_name: str | None, user_email: str | None
) -> str:
    if created_by == "system":
        return "system"
    return str(user_name or user_email or created_by)


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _model_conditions(
    org_id: str,
    *,
    dataset_id: str | None,
    job_id: str | None,
    query: str | None,
    creator_id: str | None,
    source_type: ModelSourceType | None,
    compatible_specs: tuple[CompatibleModelSpec, ...] | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        ArtifactORM.kind == "model",
        or_(TrainingJobORM.org_id == org_id, TrainingJobORM.is_public.is_(True)),
    ]
    if dataset_id is not None:
        conditions.append(TrainingJobORM.dataset_id == dataset_id)
    if job_id is not None:
        conditions.append(ArtifactORM.job_id == job_id)
    if creator_id is not None:
        conditions.append(TrainingJobORM.created_by == creator_id)
    if source_type == "dataset":
        conditions.append(TrainingJobORM.dataset_id.is_not(None))
    elif source_type == "collection":
        conditions.append(TrainingJobORM.collection_id.is_not(None))
    if compatible_specs is not None:
        compatible_conditions = [
            and_(
                TrainingJobORM.trainer_id == spec.trainer_id,
                ArtifactORM.metadata_json["model_contract"].as_string()
                == spec.model_contract,
                ArtifactORM.metadata_json["model_schema_version"].as_string()
                == spec.model_schema_version,
            )
            for spec in compatible_specs
        ]
        conditions.append(
            or_(*compatible_conditions) if compatible_conditions else false()
        )
    normalized_query = query.strip() if query is not None else ""
    if normalized_query:
        pattern = _like_pattern(normalized_query)
        conditions.append(
            or_(
                ArtifactORM.name.ilike(pattern, escape="\\"),
                ArtifactORM.id.ilike(pattern, escape="\\"),
                ArtifactORM.format.ilike(pattern, escape="\\"),
                TrainingJobORM.id.ilike(pattern, escape="\\"),
                TrainingJobORM.trainer_id.ilike(pattern, escape="\\"),
                TrainingJobORM.created_by.ilike(pattern, escape="\\"),
                DatasetORM.id.ilike(pattern, escape="\\"),
                DatasetORM.name.ilike(pattern, escape="\\"),
                DatasetCollectionORM.id.ilike(pattern, escape="\\"),
                DatasetCollectionORM.name.ilike(pattern, escape="\\"),
                UserORM.name.ilike(pattern, escape="\\"),
                UserORM.email.ilike(pattern, escape="\\"),
            )
        )
    return conditions


class ModelArtifactRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_models(
        self,
        org_id: str,
        dataset_id: str | None = None,
        job_id: str | None = None,
        query: str | None = None,
        creator_id: str | None = None,
        source_type: ModelSourceType | None = None,
        compatible_specs: tuple[CompatibleModelSpec, ...] | None = None,
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> list[Model]:
        models, _ = await self.list_models_paginated(
            org_id=org_id,
            dataset_id=dataset_id,
            job_id=job_id,
            offset=0,
            limit=None,
            query=query,
            creator_id=creator_id,
            source_type=source_type,
            compatible_specs=compatible_specs,
            sort_by=sort_by,
            sort_order=sort_order,
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
        query: str | None = None,
        creator_id: str | None = None,
        source_type: ModelSourceType | None = None,
        compatible_specs: tuple[CompatibleModelSpec, ...] | None = None,
        sort_by: ModelSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> tuple[list[Model], int]:
        async with self.session_factory() as session:
            conditions = _model_conditions(
                org_id,
                dataset_id=dataset_id,
                job_id=job_id,
                query=query,
                creator_id=creator_id,
                source_type=source_type,
                compatible_specs=compatible_specs,
            )
            sort_columns = {
                "name": ArtifactORM.name,
                "source": func.coalesce(DatasetORM.name, DatasetCollectionORM.name),
                "trainer": TrainingJobORM.trainer_id,
                "creator": func.coalesce(
                    UserORM.name, UserORM.email, TrainingJobORM.created_by
                ),
                "created_at": ArtifactORM.created_at,
            }
            sort_column = sort_columns[sort_by]
            order = sort_column.asc() if sort_order == "asc" else sort_column.desc()
            id_order = (
                ArtifactORM.id.asc() if sort_order == "asc" else ArtifactORM.id.desc()
            )

            joins = (
                select(ArtifactORM.id)
                .join(TrainingJobORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(DatasetORM, TrainingJobORM.dataset_id == DatasetORM.id)
                .outerjoin(
                    DatasetCollectionORM,
                    TrainingJobORM.collection_id == DatasetCollectionORM.id,
                )
                .outerjoin(UserORM, UserORM.id == TrainingJobORM.created_by)
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
                .order_by(order.nulls_last(), id_order)
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

    async def list_model_creators(self, org_id: str) -> list[CreatorSummary]:
        async with self.session_factory() as session:
            conditions = _model_conditions(
                org_id,
                dataset_id=None,
                job_id=None,
                query=None,
                creator_id=None,
                source_type=None,
                compatible_specs=None,
            )
            stmt = (
                select(
                    TrainingJobORM.created_by,
                    UserORM.name,
                    UserORM.email,
                )
                .join(ArtifactORM, ArtifactORM.job_id == TrainingJobORM.id)
                .outerjoin(UserORM, UserORM.id == TrainingJobORM.created_by)
                .where(*conditions)
                .distinct()
            )
            creators = [
                CreatorSummary(
                    id=str(created_by),
                    name=_creator_name(str(created_by), user_name, user_email),
                )
                for created_by, user_name, user_email in (
                    await session.execute(stmt)
                ).all()
            ]
            return sorted(
                creators, key=lambda creator: (creator.name.casefold(), creator.id)
            )

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

    async def get_org_model(self, artifact_id: str, org_id: str) -> Model | None:
        return await self.get_model(artifact_id, org_id, include_public=False)

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

    async def get_training_job_context(
        self, job_id: str, org_id: str
    ) -> tuple[str, str] | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(TrainingJobORM.created_by, TrainingJobORM.trainer_id).where(
                        TrainingJobORM.id == job_id,
                        TrainingJobORM.org_id == org_id,
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            return str(row.created_by), str(row.trainer_id)

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
