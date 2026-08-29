from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.shared.db.registry import (
    AnnotationORM,
    AnnotationVersionORM,
    DatasetORM,
    DatasetRevisionORM,
    OrganizationORM,
    PlatformPredictionORM,
    PredictionCollectionItemORM,
    PredictionCollectionORM,
    PredictionReviewActionORM,
    SampleFeatureORM,
    SampleORM,
    UserORM,
)
from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.modules.datasets.domain.repository import DatasetSortField, SortDirection
from app.shared.api.schemas import (
    Annotation,
    CreatorSummary,
    Dataset,
    ImageSourceBinding,
    Sample,
    TaskSpec,
)
from app.shared.api.schemas import DatasetStorageMode


def _assert_not_none(value: str | None) -> str:
    assert value is not None
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _to_dataset_revision(row: DatasetRevisionORM) -> DatasetRevision:
    return DatasetRevision(
        id=row.id,
        dataset_id=row.dataset_id,
        revision_number=row.revision_number,
        manifest_uri=row.manifest_uri,
        provenance=cast(dict[str, object], row.provenance),
        operation=DatasetRevisionOperation(row.operation),
        operation_ref=row.operation_ref,
        is_reproducible=row.is_reproducible,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _dataset_conditions(
    org_id: str | None,
    *,
    query: str | None,
    creator_id: str | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if org_id is not None:
        conditions.append(
            or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True))
        )
    if creator_id is not None:
        conditions.append(DatasetORM.created_by == creator_id)
    normalized_query = query.strip() if query is not None else ""
    if normalized_query:
        pattern = _like_pattern(normalized_query)
        conditions.append(
            or_(
                DatasetORM.name.ilike(pattern, escape="\\"),
                DatasetORM.id.ilike(pattern, escape="\\"),
                DatasetORM.dataset_type.ilike(pattern, escape="\\"),
                DatasetORM.created_by.ilike(pattern, escape="\\"),
                UserORM.name.ilike(pattern, escape="\\"),
                UserORM.email.ilike(pattern, escape="\\"),
                OrganizationORM.name.ilike(pattern, escape="\\"),
            )
        )
    return conditions


def _image_source_binding(value: object) -> ImageSourceBinding | None:
    if value is None:
        return None
    return ImageSourceBinding.model_validate(value)


async def _org_name_for(session: AsyncSession, org_id: str | None) -> str:
    if not org_id:
        return ""
    org_row = await session.get(OrganizationORM, org_id)
    return "" if org_row is None else org_row.name


async def _user_name_for(session: AsyncSession, user_id: str | None) -> str:
    if not user_id or user_id == "system":
        return "system"
    user_row = await session.get(UserORM, user_id)
    if user_row is None:
        return user_id
    return user_row.name or user_row.email or user_id


class DatasetSqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_dataset(
        self, dataset: Dataset, org_id: str | None = None
    ) -> Dataset:
        org_id = org_id or dataset.org_id
        if org_id is None:
            raise ValueError("org_id is required for create_dataset")
        async with self.session_factory() as session:
            org_name = await _org_name_for(session, org_id)
            creator_name = await _user_name_for(session, dataset.created_by)
            row = DatasetORM(
                id=dataset.id,
                org_id=org_id,
                name=dataset.name,
                dataset_type=dataset.dataset_type,
                dataset_meta=dataset.task_spec.model_dump(mode="json"),
                view_types=dataset.view_types,
                created_by=dataset.created_by,
                is_public=dataset.is_public,
                created_at=dataset.created_at,
                embed_config=dataset.embed_config or None,
                ls_project_id=dataset.ls_project_id,
                storage_mode=dataset.storage_mode.value,
                image_source_binding=(
                    dataset.image_source.model_dump(mode="json")
                    if dataset.image_source is not None
                    else None
                ),
            )
            session.add(row)
            await session.commit()
        return dataset.model_copy(
            update={
                "org_id": org_id,
                "org_name": org_name,
                "creator_name": creator_name,
            }
        )

    async def get_current_revision(
        self,
        dataset_id: str,
        org_id: str,
    ) -> DatasetRevision | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(DatasetRevisionORM)
                    .join(DatasetORM, DatasetORM.id == DatasetRevisionORM.dataset_id)
                    .where(
                        DatasetRevisionORM.dataset_id == dataset_id,
                        or_(
                            DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True)
                        ),
                    )
                    .order_by(DatasetRevisionORM.revision_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return None if row is None else _to_dataset_revision(row)

    async def list_current_revisions(
        self,
        dataset_ids: tuple[str, ...],
        org_id: str,
    ) -> dict[str, DatasetRevision]:
        unique_ids = tuple(dict.fromkeys(dataset_ids))
        if not unique_ids:
            return {}
        latest = (
            select(
                DatasetRevisionORM.dataset_id.label("dataset_id"),
                func.max(DatasetRevisionORM.revision_number).label("revision_number"),
            )
            .where(DatasetRevisionORM.dataset_id.in_(unique_ids))
            .group_by(DatasetRevisionORM.dataset_id)
            .subquery()
        )
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DatasetRevisionORM)
                        .join(
                            latest,
                            and_(
                                latest.c.dataset_id == DatasetRevisionORM.dataset_id,
                                latest.c.revision_number
                                == DatasetRevisionORM.revision_number,
                            ),
                        )
                        .join(
                            DatasetORM,
                            DatasetORM.id == DatasetRevisionORM.dataset_id,
                        )
                        .where(
                            DatasetRevisionORM.dataset_id.in_(unique_ids),
                            or_(
                                DatasetORM.org_id == org_id,
                                DatasetORM.is_public.is_(True),
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {row.dataset_id: _to_dataset_revision(row) for row in rows}

    async def get_revision(
        self,
        dataset_id: str,
        revision_id: str,
        org_id: str,
    ) -> DatasetRevision | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(DatasetRevisionORM)
                    .join(DatasetORM, DatasetORM.id == DatasetRevisionORM.dataset_id)
                    .where(
                        DatasetRevisionORM.id == revision_id,
                        DatasetRevisionORM.dataset_id == dataset_id,
                        or_(
                            DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True)
                        ),
                    )
                )
            ).scalar_one_or_none()
            return None if row is None else _to_dataset_revision(row)

    async def publish_revision(
        self,
        *,
        revision_id: str,
        dataset_id: str,
        org_id: str,
        manifest_uri: str,
        provenance: dict[str, object],
        operation: DatasetRevisionOperation,
        operation_ref: str | None,
        created_by: str,
    ) -> DatasetRevision:
        async with self.session_factory() as session:
            dataset = (
                await session.execute(
                    select(DatasetORM)
                    .where(
                        DatasetORM.id == dataset_id,
                        DatasetORM.org_id == org_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if dataset is None:
                raise LookupError(f"Dataset {dataset_id!r} not found")
            if operation == DatasetRevisionOperation.LEGACY_BASELINE:
                existing = (
                    await session.execute(
                        select(DatasetRevisionORM)
                        .where(DatasetRevisionORM.dataset_id == dataset_id)
                        .order_by(DatasetRevisionORM.revision_number.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return _to_dataset_revision(existing)
            current_number = await session.scalar(
                select(func.max(DatasetRevisionORM.revision_number)).where(
                    DatasetRevisionORM.dataset_id == dataset_id
                )
            )
            row = DatasetRevisionORM(
                id=revision_id,
                dataset_id=dataset_id,
                revision_number=int(current_number or 0) + 1,
                manifest_uri=manifest_uri,
                provenance=provenance,
                operation=operation.value,
                operation_ref=operation_ref,
                is_reproducible=False,
                created_by=created_by,
                created_at=_utcnow(),
            )
            session.add(row)
            await session.commit()
            return _to_dataset_revision(row)

    async def list_revisions(
        self,
        dataset_id: str,
        org_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[DatasetRevision]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DatasetRevisionORM)
                        .join(
                            DatasetORM,
                            DatasetORM.id == DatasetRevisionORM.dataset_id,
                        )
                        .where(
                            DatasetRevisionORM.dataset_id == dataset_id,
                            or_(
                                DatasetORM.org_id == org_id,
                                DatasetORM.is_public.is_(True),
                            ),
                        )
                        .order_by(DatasetRevisionORM.revision_number.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [_to_dataset_revision(row) for row in rows]

    async def count_revisions(self, dataset_id: str, org_id: str) -> int:
        async with self.session_factory() as session:
            count = await session.scalar(
                select(func.count(DatasetRevisionORM.id))
                .join(DatasetORM, DatasetORM.id == DatasetRevisionORM.dataset_id)
                .where(
                    DatasetRevisionORM.dataset_id == dataset_id,
                    or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True)),
                )
            )
            return int(count or 0)

    async def list_datasets(
        self,
        org_id: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str | None = None,
        creator_id: str | None = None,
        sort_by: DatasetSortField = "created_at",
        sort_order: SortDirection = "desc",
    ) -> list[Dataset]:
        async with self.session_factory() as session:
            sort_columns = {
                "name": DatasetORM.name,
                "dataset_type": DatasetORM.dataset_type,
                "creator": func.coalesce(
                    UserORM.name, UserORM.email, DatasetORM.created_by
                ),
                "created_at": DatasetORM.created_at,
            }
            sort_column = sort_columns[sort_by]
            order = sort_column.asc() if sort_order == "asc" else sort_column.desc()
            id_order = (
                DatasetORM.id.asc() if sort_order == "asc" else DatasetORM.id.desc()
            )
            stmt = (
                select(DatasetORM, OrganizationORM.name, UserORM.name, UserORM.email)
                .outerjoin(OrganizationORM, OrganizationORM.id == DatasetORM.org_id)
                .outerjoin(UserORM, UserORM.id == DatasetORM.created_by)
                .order_by(order.nulls_last(), id_order)
            )
            stmt = stmt.where(
                *_dataset_conditions(
                    org_id,
                    query=query,
                    creator_id=creator_id,
                )
            )
            if offset:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).all()
            return [
                Dataset(
                    id=r.id,
                    org_id=r.org_id,
                    org_name=str(org_name or ""),
                    creator_name=str(user_name or user_email or r.created_by),
                    name=r.name,
                    dataset_type=r.dataset_type,
                    task_spec=cast(TaskSpec, r.dataset_meta),
                    view_types=cast(list[str], r.view_types),
                    created_by=r.created_by,
                    is_public=r.is_public,
                    created_at=r.created_at,
                    embed_config=r.embed_config or {},
                    ls_project_id=r.ls_project_id,
                    storage_mode=cast(DatasetStorageMode, r.storage_mode),
                    dataset_meta=r.dataset_meta,
                    image_source=_image_source_binding(r.image_source_binding),
                )
                for r, org_name, user_name, user_email in rows
            ]

    async def list_dataset_creators(
        self,
        org_id: str | None = None,
    ) -> list[CreatorSummary]:
        async with self.session_factory() as session:
            stmt = (
                select(
                    DatasetORM.created_by,
                    UserORM.name,
                    UserORM.email,
                )
                .outerjoin(UserORM, UserORM.id == DatasetORM.created_by)
                .where(
                    *_dataset_conditions(
                        org_id,
                        query=None,
                        creator_id=None,
                    )
                )
                .distinct()
            )
            creators = [
                CreatorSummary(
                    id=str(created_by),
                    name=str(user_name or user_email or created_by),
                )
                for created_by, user_name, user_email in (
                    await session.execute(stmt)
                ).all()
            ]
            return sorted(
                creators, key=lambda creator: (creator.name.casefold(), creator.id)
            )

    async def count_datasets(
        self,
        org_id: str | None = None,
        *,
        query: str | None = None,
        creator_id: str | None = None,
    ) -> int:
        async with self.session_factory() as session:
            stmt = (
                select(func.count(DatasetORM.id))
                .outerjoin(OrganizationORM, OrganizationORM.id == DatasetORM.org_id)
                .outerjoin(UserORM, UserORM.id == DatasetORM.created_by)
                .where(
                    *_dataset_conditions(
                        org_id,
                        query=query,
                        creator_id=creator_id,
                    )
                )
            )
            return int((await session.execute(stmt)).scalar_one())

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
                creator_name=await _user_name_for(session, row.created_by),
                name=row.name,
                dataset_type=row.dataset_type,
                task_spec=cast(TaskSpec, row.dataset_meta),
                view_types=cast(list[str], row.view_types),
                created_by=row.created_by,
                is_public=row.is_public,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
                storage_mode=cast(DatasetStorageMode, row.storage_mode),
                dataset_meta=row.dataset_meta,
                image_source=_image_source_binding(row.image_source_binding),
            )

    async def list_dataset_names(
        self, dataset_ids: list[str], org_id: str | None = None
    ) -> dict[str, str]:
        if not dataset_ids:
            return {}
        unique_ids = list(dict.fromkeys(dataset_ids))
        async with self.session_factory() as session:
            stmt = select(DatasetORM.id, DatasetORM.name).where(
                DatasetORM.id.in_(unique_ids)
            )
            if org_id is not None:
                stmt = stmt.where(
                    or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True))
                )
            rows = (await session.execute(stmt)).all()
            return {str(dataset_id): str(name) for dataset_id, name in rows}

    async def list_datasets_by_ids(
        self, dataset_ids: list[str], org_id: str | None = None
    ) -> list[Dataset]:
        if not dataset_ids:
            return []
        unique_ids = list(dict.fromkeys(dataset_ids))
        async with self.session_factory() as session:
            stmt = (
                select(DatasetORM, OrganizationORM.name, UserORM.name, UserORM.email)
                .outerjoin(OrganizationORM, OrganizationORM.id == DatasetORM.org_id)
                .outerjoin(UserORM, UserORM.id == DatasetORM.created_by)
                .where(DatasetORM.id.in_(unique_ids))
            )
            if org_id is not None:
                stmt = stmt.where(
                    or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True))
                )
            rows = (await session.execute(stmt)).all()
            by_id = {
                row.id: Dataset(
                    id=row.id,
                    org_id=row.org_id,
                    org_name=str(org_name or ""),
                    creator_name=str(user_name or user_email or row.created_by),
                    name=row.name,
                    dataset_type=row.dataset_type,
                    task_spec=cast(TaskSpec, row.dataset_meta),
                    view_types=cast(list[str], row.view_types),
                    created_by=row.created_by,
                    is_public=row.is_public,
                    created_at=row.created_at,
                    embed_config=row.embed_config or {},
                    ls_project_id=row.ls_project_id,
                    storage_mode=cast(DatasetStorageMode, row.storage_mode),
                    dataset_meta=row.dataset_meta,
                    image_source=_image_source_binding(row.image_source_binding),
                )
                for row, org_name, user_name, user_email in rows
            }
            return [
                by_id[dataset_id] for dataset_id in unique_ids if dataset_id in by_id
            ]

    async def list_datasets_for_sc_inspections(
        self,
        inspection_times: Sequence[str],
        org_id: str | None = None,
    ) -> list[Dataset]:
        unique_times = list(dict.fromkeys(inspection_times))
        if not unique_times:
            return []
        async with self.session_factory() as session:
            stmt = (
                select(DatasetORM, OrganizationORM.name, UserORM.name, UserORM.email)
                .outerjoin(OrganizationORM, OrganizationORM.id == DatasetORM.org_id)
                .outerjoin(UserORM, UserORM.id == DatasetORM.created_by)
                .where(
                    DatasetORM.dataset_meta["source_inspection_time"]
                    .as_string()
                    .in_(unique_times)
                )
                .order_by(DatasetORM.created_at.desc(), DatasetORM.id.desc())
            )
            if org_id is not None:
                stmt = stmt.where(
                    or_(DatasetORM.org_id == org_id, DatasetORM.is_public.is_(True))
                )
            rows = (await session.execute(stmt)).all()
            return [
                Dataset(
                    id=row.id,
                    org_id=row.org_id,
                    org_name=str(org_name or ""),
                    creator_name=str(user_name or user_email or row.created_by),
                    name=row.name,
                    dataset_type=row.dataset_type,
                    task_spec=cast(TaskSpec, row.dataset_meta),
                    view_types=cast(list[str], row.view_types),
                    created_by=row.created_by,
                    is_public=row.is_public,
                    created_at=row.created_at,
                    embed_config=row.embed_config or {},
                    ls_project_id=row.ls_project_id,
                    storage_mode=cast(DatasetStorageMode, row.storage_mode),
                    dataset_meta=row.dataset_meta,
                    image_source=_image_source_binding(row.image_source_binding),
                )
                for row, org_name, user_name, user_email in rows
            ]

    async def rename_dataset(
        self, dataset_id: str, *, name: str, org_id: str | None = None
    ) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
            row.name = name
            await session.commit()
            return Dataset(
                id=row.id,
                org_id=row.org_id,
                org_name=await _org_name_for(session, row.org_id),
                creator_name=await _user_name_for(session, row.created_by),
                name=row.name,
                dataset_type=row.dataset_type,
                task_spec=cast(TaskSpec, row.dataset_meta),
                view_types=cast(list[str], row.view_types),
                created_by=row.created_by,
                is_public=row.is_public,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
                storage_mode=cast(DatasetStorageMode, row.storage_mode),
                dataset_meta=row.dataset_meta,
                image_source=_image_source_binding(row.image_source_binding),
            )

    async def delete_dataset(self, dataset_id: str, org_id: str | None = None) -> bool:
        async with self.session_factory() as session:
            dataset = await session.get(DatasetORM, dataset_id)
            if dataset is None:
                return False
            if org_id is not None and dataset.org_id != org_id:
                return False

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
            await session.delete(dataset)
            await session.commit()
            return True

    async def update_dataset_meta(
        self,
        dataset_id: str,
        meta_update: dict,
        *,
        org_id: str | None = None,
    ) -> Dataset | None:
        async with self.session_factory() as session:
            row = await session.get(DatasetORM, dataset_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id:
                return None
            current = dict(row.dataset_meta or {})
            row.dataset_meta = {**current, **meta_update}
            await session.commit()
            return Dataset(
                id=row.id,
                org_id=row.org_id,
                org_name=await _org_name_for(session, row.org_id),
                created_by=row.created_by,
                creator_name=await _user_name_for(session, row.created_by),
                name=row.name,
                dataset_type=row.dataset_type,
                task_spec=cast(TaskSpec, row.dataset_meta),
                view_types=cast(list[str], row.view_types),
                is_public=row.is_public,
                created_at=row.created_at,
                embed_config=row.embed_config or {},
                ls_project_id=row.ls_project_id,
                storage_mode=cast(DatasetStorageMode, row.storage_mode),
                dataset_meta=row.dataset_meta,
                image_source=_image_source_binding(row.image_source_binding),
            )

    # ── sample / annotation methods (db_full only) ──────────────────────────
    # DEPRECATED(T27): These methods operate directly on SampleORM / AnnotationORM
    # and serve only the DB_FULL storage mode.  External callers should migrate
    # to DatasetStorageAgg via DatasetStorageFactory for cross-mode compatibility.
    # Internal callers (DbFullSampleAccess) remain as transitional backends.
    # DO NOT add new callers to these methods.

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

    async def existing_sample_ids(self, sample_ids: set[str]) -> set[str]:
        if not sample_ids:
            return set()
        ordered_ids = list(sample_ids)
        existing: set[str] = set()
        async with self.session_factory() as session:
            for offset in range(0, len(ordered_ids), 500):
                existing.update(
                    (
                        await session.execute(
                            select(SampleORM.id).where(
                                SampleORM.id.in_(ordered_ids[offset : offset + 500])
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
        return existing

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

    # DEPRECATED(T27): Direct SampleORM query — use storage.get_sample() via
    # DatasetStorageFactory for cross-mode compatibility.
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

    async def get_annotation_stats(self, dataset_id: str) -> dict:
        """Return aggregate annotation statistics for a dataset.

        Returns a dict with keys: total_samples, annotated_samples,
        unlabeled_samples, label_counts.
        """
        from sqlalchemy import alias, and_

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

            AnnAlias = alias(AnnotationORM.__table__, name="ann_stats")

            # Base: all samples in dataset LEFT JOIN to latest annotation
            base = (
                select(
                    SampleORM.id.label("sample_id"),
                    AnnAlias.c.label.label("ann_label"),
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
                .subquery("base_stats")
            )

            # Total samples
            total_stmt = select(func.count()).select_from(base)
            total_samples = await session.scalar(total_stmt) or 0

            # Annotated samples (ann_label IS NOT NULL)
            annotated_stmt = select(func.count()).select_from(
                select(base.c.sample_id).where(base.c.ann_label.isnot(None)).subquery()
            )
            annotated_samples = await session.scalar(annotated_stmt) or 0

            # Label counts
            label_count_stmt = (
                select(
                    base.c.ann_label,
                    func.count().label("cnt"),
                )
                .where(base.c.ann_label.isnot(None))
                .group_by(base.c.ann_label)
            )
            label_rows = (await session.execute(label_count_stmt)).all()
            label_counts = {row[0]: row[1] for row in label_rows}

            return {
                "total_samples": total_samples,
                "annotated_samples": annotated_samples,
                "unlabeled_samples": total_samples - annotated_samples,
                "label_counts": label_counts,
            }

    # ── annotation methods (db_full only, FK to samples.id) ─────────────────
    # DEPRECATED(T27): Use DatasetStorageAgg.{create_annotations,update_annotations,
    # delete_annotations,get_annotation_stats} via DatasetStorageFactory instead.

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
            return [
                Annotation(
                    id=r.id,
                    sample_id=r.sample_id,
                    label=r.label,
                    annotation_value=r.annotation_value,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def list_annotations_for_sample(self, sample_id: str) -> list[Annotation]:
        async with self.session_factory() as session:
            stmt = select(AnnotationORM).where(AnnotationORM.sample_id == sample_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Annotation(
                    id=r.id,
                    sample_id=r.sample_id,
                    label=r.label,
                    annotation_value=r.annotation_value,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def get_annotation(self, annotation_id: str) -> Annotation | None:
        async with self.session_factory() as session:
            row = await session.get(AnnotationORM, annotation_id)
            if row is None:
                return None
            return Annotation(
                id=row.id,
                sample_id=row.sample_id,
                label=row.label,
                annotation_value=row.annotation_value,
                created_by=row.created_by,
                created_at=row.created_at,
            )

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
