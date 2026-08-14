from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.dataset_collections.domain.errors import (
    DatasetCollectionConflictError,
    DatasetCollectionNotFoundError,
)
from app.modules.dataset_collections.domain.models import (
    DatasetCollection,
    DatasetCollectionMember,
    DatasetCollectionRevision,
    NewCollectionMember,
)
from app.shared.db.models.dataset_collections import (
    DatasetCollectionMemberORM,
    DatasetCollectionORM,
    DatasetCollectionRevisionORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _collection(row: DatasetCollectionORM) -> DatasetCollection:
    return DatasetCollection(
        id=row.id,
        org_id=row.org_id,
        name=row.name,
        description=row.description,
        target_view_id=row.target_view_id,
        target_view_contract=row.target_view_contract,
        target_schema_version=row.target_schema_version,
        duplicate_policy=row.duplicate_policy,
        missing_data_policy=row.missing_data_policy,
        definition_version=row.definition_version,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _member(row: DatasetCollectionMemberORM) -> DatasetCollectionMember:
    return DatasetCollectionMember(
        id=row.id,
        collection_id=row.collection_id,
        source_dataset_id=row.source_dataset_ref,
        position=row.position,
        linked_definition_version=row.linked_definition_version,
        unlinked_definition_version=row.unlinked_definition_version,
        filter_spec=cast(dict[str, object], row.filter_spec),
        label_mapping=cast(dict[str, str], row.label_mapping),
        sampling_spec=cast(dict[str, object], row.sampling_spec),
        linked_by=row.linked_by,
        linked_at=row.linked_at,
        unlinked_by=row.unlinked_by,
        unlinked_at=row.unlinked_at,
    )


def _revision(row: DatasetCollectionRevisionORM) -> DatasetCollectionRevision:
    return DatasetCollectionRevision(
        id=row.id,
        collection_id=row.collection_id,
        revision_number=row.revision_number,
        definition_version=row.definition_version,
        definition_hash=row.definition_hash,
        target_view_id=row.target_view_id,
        target_view_contract=row.target_view_contract,
        target_schema_version=row.target_schema_version,
        status=row.status,
        source_snapshot=tuple(cast(list[dict[str, object]], row.source_snapshot)),
        row_count=row.row_count,
        label_counts={
            str(key): int(cast(int | str, value))
            for key, value in cast(dict[str, object], row.label_counts).items()
        },
        manifest_uri=row.manifest_uri,
        provenance_uri=row.provenance_uri,
        trigger_kind=row.trigger_kind,
        trigger_ref=row.trigger_ref,
        created_by=row.created_by,
        created_at=row.created_at,
        error_code=row.error_code,
        error_detail=row.error_detail,
    )


class DatasetCollectionSqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_collection(
        self, collection: DatasetCollection
    ) -> DatasetCollection:
        async with self._session_factory() as session:
            row = DatasetCollectionORM(
                id=collection.id,
                org_id=collection.org_id,
                name=collection.name,
                description=collection.description,
                target_view_id=collection.target_view_id,
                target_view_contract=collection.target_view_contract,
                target_schema_version=collection.target_schema_version,
                duplicate_policy=collection.duplicate_policy,
                missing_data_policy=collection.missing_data_policy,
                definition_version=collection.definition_version,
                created_by=collection.created_by,
                created_at=collection.created_at,
                updated_at=collection.updated_at,
            )
            session.add(row)
            await session.commit()
            return _collection(row)

    async def list_collections(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[DatasetCollection], int]:
        async with self._session_factory() as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(DatasetCollectionORM)
                    .where(DatasetCollectionORM.org_id == org_id)
                )
                or 0
            )
            rows = (
                await session.execute(
                    select(DatasetCollectionORM)
                    .where(DatasetCollectionORM.org_id == org_id)
                    .order_by(
                        DatasetCollectionORM.updated_at.desc(),
                        DatasetCollectionORM.id.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).scalars()
            return [_collection(row) for row in rows], total

    async def get_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection | None:
        async with self._session_factory() as session:
            row = await self._collection_row(session, collection_id, org_id)
            return _collection(row) if row is not None else None

    async def update_collection(
        self,
        collection_id: str,
        org_id: str,
        *,
        name: str | None,
        description: str | None,
    ) -> DatasetCollection | None:
        async with self._session_factory() as session:
            row = await self._collection_row(
                session, collection_id, org_id, for_update=True
            )
            if row is None:
                return None
            if name is not None:
                row.name = name
            if description is not None:
                row.description = description
            row.updated_at = _utcnow()
            await session.commit()
            return _collection(row)

    async def delete_collection(
        self, collection_id: str, org_id: str
    ) -> tuple[str, ...] | None:
        async with self._session_factory() as session:
            row = await self._collection_row(
                session, collection_id, org_id, for_update=True
            )
            if row is None:
                return None
            revision_artifacts = await session.execute(
                select(
                    DatasetCollectionRevisionORM.manifest_uri,
                    DatasetCollectionRevisionORM.provenance_uri,
                ).where(DatasetCollectionRevisionORM.collection_id == collection_id)
            )
            artifact_uris = tuple(
                dict.fromkeys(
                    uri
                    for revision_row in revision_artifacts
                    for uri in revision_row
                    if uri is not None
                )
            )
            await session.delete(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                raise DatasetCollectionConflictError(
                    "collection_in_use",
                    "Collection is referenced by a training or prediction job",
                ) from exc
            return artifact_uris

    async def list_active_members(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionMember]:
        async with self._session_factory() as session:
            collection = await self._collection_row(session, collection_id, org_id)
            if collection is None:
                raise DatasetCollectionNotFoundError("Dataset collection not found")
            rows = await self._active_member_rows(session, collection_id)
            return [_member(row) for row in rows]

    async def link_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        async with self._session_factory() as session:
            collection = await self._locked_definition(
                session, collection_id, org_id, expected_definition_version
            )
            new_version = collection.definition_version + 1
            linked_at = _utcnow()
            session.add_all(
                [
                    DatasetCollectionMemberORM(
                        id=str(uuid4()),
                        collection_id=collection.id,
                        source_dataset_id=item.source_dataset_id,
                        source_dataset_ref=item.source_dataset_id,
                        position=item.position,
                        linked_definition_version=new_version,
                        filter_spec=item.filter_spec,
                        label_mapping=item.label_mapping,
                        sampling_spec=item.sampling_spec,
                        linked_by=actor_id,
                        linked_at=linked_at,
                    )
                    for item in members
                ]
            )
            collection.definition_version = new_version
            collection.updated_at = linked_at
            try:
                await session.flush()
            except IntegrityError as exc:
                raise DatasetCollectionConflictError(
                    "dataset_already_linked",
                    "One or more datasets are already linked to the collection",
                ) from exc
            rows = await self._active_member_rows(session, collection.id)
            result = (_collection(collection), [_member(row) for row in rows])
            await session.commit()
            return result

    async def unlink_member(
        self,
        collection_id: str,
        member_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        async with self._session_factory() as session:
            collection = await self._locked_definition(
                session, collection_id, org_id, expected_definition_version
            )
            member = (
                await session.execute(
                    select(DatasetCollectionMemberORM)
                    .where(DatasetCollectionMemberORM.id == member_id)
                    .where(DatasetCollectionMemberORM.collection_id == collection.id)
                    .where(DatasetCollectionMemberORM.unlinked_at.is_(None))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if member is None:
                raise DatasetCollectionConflictError(
                    "member_not_active", "Collection member is not active"
                )
            unlinked_at = _utcnow()
            new_version = collection.definition_version + 1
            member.unlinked_definition_version = new_version
            member.unlinked_by = actor_id
            member.unlinked_at = unlinked_at
            collection.definition_version = new_version
            collection.updated_at = unlinked_at
            await session.flush()
            rows = await self._active_member_rows(session, collection.id)
            result = (_collection(collection), [_member(row) for row in rows])
            await session.commit()
            return result

    async def replace_members(
        self,
        collection_id: str,
        org_id: str,
        *,
        expected_definition_version: int,
        members: tuple[NewCollectionMember, ...],
        actor_id: str,
    ) -> tuple[DatasetCollection, list[DatasetCollectionMember]]:
        async with self._session_factory() as session:
            collection = await self._locked_definition(
                session, collection_id, org_id, expected_definition_version
            )
            active_rows = await self._active_member_rows(
                session, collection.id, for_update=True
            )
            active_by_dataset = {row.source_dataset_ref: row for row in active_rows}
            requested_by_dataset = {item.source_dataset_id: item for item in members}
            changed_at = _utcnow()
            new_version = collection.definition_version + 1
            for dataset_id, row in active_by_dataset.items():
                requested = requested_by_dataset.get(dataset_id)
                if requested is None:
                    row.unlinked_definition_version = new_version
                    row.unlinked_by = actor_id
                    row.unlinked_at = changed_at
                    continue
                row.position = requested.position
                row.filter_spec = requested.filter_spec
                row.label_mapping = requested.label_mapping
                row.sampling_spec = requested.sampling_spec
            for dataset_id, requested in requested_by_dataset.items():
                if dataset_id in active_by_dataset:
                    continue
                session.add(
                    DatasetCollectionMemberORM(
                        id=str(uuid4()),
                        collection_id=collection.id,
                        source_dataset_id=dataset_id,
                        source_dataset_ref=dataset_id,
                        position=requested.position,
                        linked_definition_version=new_version,
                        filter_spec=requested.filter_spec,
                        label_mapping=requested.label_mapping,
                        sampling_spec=requested.sampling_spec,
                        linked_by=actor_id,
                        linked_at=changed_at,
                    )
                )
            collection.definition_version = new_version
            collection.updated_at = changed_at
            try:
                await session.flush()
            except IntegrityError as exc:
                raise DatasetCollectionConflictError(
                    "dataset_already_linked",
                    "The replacement contains a dataset that is already linked",
                ) from exc
            rows = await self._active_member_rows(session, collection.id)
            result = (_collection(collection), [_member(row) for row in rows])
            await session.commit()
            return result

    async def create_revision(
        self,
        revision: DatasetCollectionRevision,
        org_id: str,
        *,
        expected_definition_version: int,
    ) -> DatasetCollectionRevision:
        async with self._session_factory() as session:
            await self._locked_definition(
                session,
                revision.collection_id,
                org_id,
                expected_definition_version,
            )
            row = DatasetCollectionRevisionORM(
                id=revision.id,
                collection_id=revision.collection_id,
                revision_number=revision.revision_number,
                definition_version=revision.definition_version,
                definition_hash=revision.definition_hash,
                target_view_id=revision.target_view_id,
                target_view_contract=revision.target_view_contract,
                target_schema_version=revision.target_schema_version,
                status=revision.status,
                source_snapshot=list(revision.source_snapshot),
                row_count=revision.row_count,
                label_counts=revision.label_counts,
                manifest_uri=revision.manifest_uri,
                provenance_uri=revision.provenance_uri,
                trigger_kind=revision.trigger_kind,
                trigger_ref=revision.trigger_ref,
                created_by=revision.created_by,
                created_at=revision.created_at,
                error_code=revision.error_code,
                error_detail=revision.error_detail,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                raise DatasetCollectionConflictError(
                    "revision_conflict",
                    "Another revision was created concurrently",
                ) from exc
            return _revision(row)

    async def list_revisions(
        self, collection_id: str, org_id: str
    ) -> list[DatasetCollectionRevision]:
        async with self._session_factory() as session:
            collection = await self._collection_row(session, collection_id, org_id)
            if collection is None:
                raise DatasetCollectionNotFoundError("Dataset collection not found")
            rows = (
                await session.execute(
                    select(DatasetCollectionRevisionORM)
                    .where(DatasetCollectionRevisionORM.collection_id == collection_id)
                    .order_by(DatasetCollectionRevisionORM.revision_number.desc())
                )
            ).scalars()
            return [_revision(row) for row in rows]

    async def get_revision(
        self, collection_id: str, revision_id: str, org_id: str
    ) -> DatasetCollectionRevision | None:
        async with self._session_factory() as session:
            collection = await self._collection_row(session, collection_id, org_id)
            if collection is None:
                return None
            row = (
                await session.execute(
                    select(DatasetCollectionRevisionORM)
                    .where(DatasetCollectionRevisionORM.id == revision_id)
                    .where(DatasetCollectionRevisionORM.collection_id == collection_id)
                )
            ).scalar_one_or_none()
            return _revision(row) if row is not None else None

    async def next_revision_number(self, collection_id: str, org_id: str) -> int:
        async with self._session_factory() as session:
            collection = await self._collection_row(session, collection_id, org_id)
            if collection is None:
                raise DatasetCollectionNotFoundError("Dataset collection not found")
            current = await session.scalar(
                select(func.max(DatasetCollectionRevisionORM.revision_number)).where(
                    DatasetCollectionRevisionORM.collection_id == collection_id
                )
            )
            return int(current or 0) + 1

    async def has_dataset_references(self, dataset_id: str, org_id: str) -> bool:
        async with self._session_factory() as session:
            active = await session.scalar(
                select(func.count())
                .select_from(DatasetCollectionMemberORM)
                .join(
                    DatasetCollectionORM,
                    DatasetCollectionORM.id == DatasetCollectionMemberORM.collection_id,
                )
                .where(DatasetCollectionORM.org_id == org_id)
                .where(DatasetCollectionMemberORM.source_dataset_id == dataset_id)
                .where(DatasetCollectionMemberORM.unlinked_at.is_(None))
            )
            if int(active or 0) > 0:
                return True
            snapshots = (
                await session.execute(
                    select(DatasetCollectionRevisionORM.source_snapshot)
                    .join(
                        DatasetCollectionORM,
                        DatasetCollectionORM.id
                        == DatasetCollectionRevisionORM.collection_id,
                    )
                    .where(DatasetCollectionORM.org_id == org_id)
                )
            ).scalars()
            return any(
                any(
                    str(item.get("source_dataset_id", "")) == dataset_id
                    for item in cast(list[dict[str, object]], snapshot)
                )
                for snapshot in snapshots
            )

    async def _locked_definition(
        self,
        session: AsyncSession,
        collection_id: str,
        org_id: str,
        expected_definition_version: int,
    ) -> DatasetCollectionORM:
        row = await self._collection_row(
            session, collection_id, org_id, for_update=True
        )
        if row is None:
            raise DatasetCollectionNotFoundError("Dataset collection not found")
        if row.definition_version != expected_definition_version:
            raise DatasetCollectionConflictError(
                "definition_version_conflict",
                "Collection definition changed; reload before applying this operation",
            )
        return row

    @staticmethod
    async def _collection_row(
        session: AsyncSession,
        collection_id: str,
        org_id: str,
        *,
        for_update: bool = False,
    ) -> DatasetCollectionORM | None:
        stmt = (
            select(DatasetCollectionORM)
            .where(DatasetCollectionORM.id == collection_id)
            .where(DatasetCollectionORM.org_id == org_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _active_member_rows(
        session: AsyncSession,
        collection_id: str,
        *,
        for_update: bool = False,
    ) -> list[DatasetCollectionMemberORM]:
        stmt = (
            select(DatasetCollectionMemberORM)
            .where(DatasetCollectionMemberORM.collection_id == collection_id)
            .where(DatasetCollectionMemberORM.unlinked_at.is_(None))
            .order_by(
                DatasetCollectionMemberORM.position.asc(),
                DatasetCollectionMemberORM.id.asc(),
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list((await session.execute(stmt)).scalars())
