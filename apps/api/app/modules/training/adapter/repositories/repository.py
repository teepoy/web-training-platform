from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.training.domain.repository import ActiveTrainingExecution
from app.shared.api.schemas import (
    ArtifactRef,
    TrainingEvent,
    TrainingJob,
)
from app.shared.api.schemas import JobStatus
from app.shared.db.models.artifacts import ArtifactORM
from app.shared.db.models.auth import OrganizationORM
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


class TrainingJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def has_active_jobs(self, *, dataset_id: str, org_id: str) -> bool:
        async with self.session_factory() as session:
            job_id = await session.scalar(
                select(TrainingJobORM.id)
                .where(
                    TrainingJobORM.dataset_id == dataset_id,
                    TrainingJobORM.org_id == org_id,
                    TrainingJobORM.status.in_(
                        [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
                    ),
                )
                .limit(1)
            )
            return job_id is not None

    async def set_job_public(self, job_id: str, is_public: bool) -> bool:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return False
            row.is_public = is_public
            await session.commit()
            return True

    async def create_job(
        self, job: TrainingJob, org_id: str | None = None, user_id: str | None = None
    ) -> TrainingJob:
        org_id = org_id or job.org_id
        if org_id is None:
            raise ValueError("org_id is required for create_job")
        async with self.session_factory() as session:
            org_name = await _org_name_for(session, org_id)
            session.add(
                TrainingJobORM(
                    id=job.id,
                    org_id=org_id,
                    dataset_id=job.dataset_id,
                    dataset_revision_id=job.dataset_revision_id,
                    collection_id=job.collection_id,
                    collection_revision_id=job.collection_revision_id,
                    trainer_id=job.trainer_id,
                    status=job.status.value,
                    is_public=job.is_public,
                    created_by=job.created_by,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    user_id=user_id,
                )
            )
            await session.flush()
            session.add(JobUserStateORM(job_id=job.id, user_left=False))
            await session.commit()
        return job.model_copy(update={"org_id": org_id, "org_name": org_name})

    async def set_job_external_id(self, job_id: str, external_job_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return
            row.external_job_id = external_job_id
            row.updated_at = _utcnow()
            await session.commit()

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
    ) -> bool:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return False
            if row.status == status.value:
                return False
            row.status = status.value
            row.updated_at = _utcnow()
            await session.commit()
            return True

    async def get_job_external_id(
        self,
        job_id: str,
        org_id: str | None = None,
    ) -> str | None:
        async with self.session_factory() as session:
            conditions = [TrainingJobORM.id == job_id]
            if org_id is not None:
                conditions.append(TrainingJobORM.org_id == org_id)
            return await session.scalar(
                select(TrainingJobORM.external_job_id).where(*conditions)
            )

    async def list_active_executions(self) -> list[ActiveTrainingExecution]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        TrainingJobORM.id,
                        TrainingJobORM.external_job_id,
                        TrainingJobORM.status,
                    ).where(
                        TrainingJobORM.external_job_id.is_not(None),
                        TrainingJobORM.status.in_(
                            [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
                        ),
                    )
                )
            ).all()
            return [
                ActiveTrainingExecution(
                    job_id=str(job_id),
                    external_job_id=str(external_job_id),
                    status=JobStatus(str(status)),
                )
                for job_id, external_job_id, status in rows
            ]

    async def list_jobs(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        *,
        include_artifacts: bool = False,
    ) -> list[TrainingJob]:
        items, _ = await self.list_jobs_paginated(
            org_id=org_id,
            dataset_id=dataset_id,
            offset=0,
            limit=None,
            include_artifacts=include_artifacts,
        )
        return items

    async def list_jobs_paginated(
        self,
        org_id: str | None = None,
        dataset_id: str | None = None,
        *,
        offset: int = 0,
        limit: int | None = 50,
        include_artifacts: bool = True,
    ) -> tuple[list[TrainingJob], int]:
        async with self.session_factory() as session:
            conditions = []
            if org_id is not None:
                conditions.append(
                    or_(
                        TrainingJobORM.org_id == org_id,
                        TrainingJobORM.is_public.is_(True),
                    )
                )  # noqa: E712
            if dataset_id is not None:
                conditions.append(TrainingJobORM.dataset_id == dataset_id)

            total = int(
                await session.scalar(
                    select(func.count()).select_from(TrainingJobORM).where(*conditions)
                )
                or 0
            )
            stmt = (
                select(TrainingJobORM, OrganizationORM.name)
                .outerjoin(
                    OrganizationORM,
                    OrganizationORM.id == TrainingJobORM.org_id,
                )
                .where(*conditions)
                .order_by(
                    TrainingJobORM.created_at.desc(),
                    TrainingJobORM.id.desc(),
                )
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).all()
            job_ids = [row.id for row, _ in rows]
            artifacts_by_job: dict[str, list[ArtifactRef]] = {
                job_id: [] for job_id in job_ids
            }
            if include_artifacts and job_ids:
                artifact_rows = (
                    (
                        await session.execute(
                            select(ArtifactORM)
                            .where(ArtifactORM.job_id.in_(job_ids))
                            .order_by(ArtifactORM.created_at, ArtifactORM.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for artifact in artifact_rows:
                    if artifact.job_id is None:
                        raise RuntimeError(
                            f"Artifact {artifact.id} is missing its training job"
                        )
                    artifacts_by_job[artifact.job_id].append(
                        self._artifact_to_domain(artifact)
                    )

            return (
                [
                    self._job_to_domain(
                        row,
                        artifacts_by_job[row.id],
                        str(org_name or ""),
                    )
                    for row, org_name in rows
                ],
                total,
            )

    async def get_job(
        self, job_id: str, org_id: str | None = None
    ) -> TrainingJob | None:
        async with self.session_factory() as session:
            row = await session.get(TrainingJobORM, job_id)
            if row is None:
                return None
            if org_id is not None and row.org_id != org_id and not row.is_public:
                return None
            arts = await self._list_artifacts_by_job_in_session(session, row.id)
            return self._job_to_domain(
                row, arts, await _org_name_for(session, row.org_id)
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
            rows = (
                (
                    await session.execute(
                        select(TrainingEventORM)
                        .where(TrainingEventORM.job_id == job_id)
                        .order_by(TrainingEventORM.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._event_to_domain(r) for r in rows]

    async def list_events_after(
        self,
        job_id: str,
        after_id: int,
        limit: int = 200,
    ) -> tuple[list[TrainingEvent], int]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(TrainingEventORM)
                        .where(
                            TrainingEventORM.job_id == job_id,
                            TrainingEventORM.id > after_id,
                        )
                        .order_by(TrainingEventORM.id.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            next_after_id = rows[-1].id if rows else after_id
            return [self._event_to_domain(row) for row in rows], next_after_id

    async def list_events_paginated(
        self, job_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[TrainingEvent], int]:
        async with self.session_factory() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(TrainingEventORM)
                .where(TrainingEventORM.job_id == job_id)
            )
            rows = (
                (
                    await session.execute(
                        select(TrainingEventORM)
                        .where(TrainingEventORM.job_id == job_id)
                        .order_by(TrainingEventORM.id.asc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            items = [self._event_to_domain(r) for r in rows]
            return items, max(total or 0, len(items))

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

    async def upsert_artifacts(
        self,
        job_id: str,
        artifacts: list[ArtifactRef],
    ) -> None:
        """Idempotently persist runtime artifacts with caller-stable IDs."""

        async with self.session_factory() as session:
            for artifact in artifacts:
                row = await session.get(ArtifactORM, artifact.id)
                if row is None:
                    session.add(
                        ArtifactORM(
                            id=artifact.id,
                            job_id=job_id,
                            uri=artifact.uri,
                            kind=artifact.kind,
                            metadata_json=artifact.metadata,
                            name=artifact.name,
                            file_size=artifact.file_size,
                            file_hash=artifact.file_hash,
                            format=artifact.format,
                            created_at=artifact.created_at,
                        )
                    )
                    continue
                if row.job_id not in {None, job_id}:
                    raise ValueError(
                        f"Artifact {artifact.id!r} belongs to another training job"
                    )
                row.job_id = job_id
                row.uri = artifact.uri
                row.kind = artifact.kind
                row.metadata_json = artifact.metadata
                row.name = artifact.name
                row.file_size = artifact.file_size
                row.file_hash = artifact.file_hash
                row.format = artifact.format
                if artifact.created_at is not None:
                    row.created_at = artifact.created_at
            await session.commit()

    async def get_artifact(self, artifact_id: str) -> ArtifactRef | None:
        async with self.session_factory() as session:
            row = await session.get(ArtifactORM, artifact_id)
            if row is None:
                return None
            return self._artifact_to_domain(row)

    async def _list_artifacts_by_job_in_session(
        self, session: AsyncSession, job_id: str
    ) -> list[ArtifactRef]:
        rows = (
            (
                await session.execute(
                    select(ArtifactORM).where(ArtifactORM.job_id == job_id)
                )
            )
            .scalars()
            .all()
        )
        return [self._artifact_to_domain(r) for r in rows]

    @staticmethod
    def _job_to_domain(
        row: TrainingJobORM, artifacts: list[ArtifactRef], org_name: str
    ) -> TrainingJob:
        return TrainingJob(
            id=row.id,
            org_id=row.org_id,
            org_name=org_name,
            dataset_id=row.dataset_id,
            dataset_revision_id=row.dataset_revision_id,
            collection_id=row.collection_id,
            collection_revision_id=row.collection_revision_id,
            trainer_id=row.trainer_id,
            status=cast(JobStatus, row.status),
            created_by=row.created_by,
            is_public=row.is_public,
            created_at=row.created_at,
            updated_at=row.updated_at,
            external_job_id=row.external_job_id,
            artifact_refs=artifacts,
        )

    @staticmethod
    def _event_to_domain(row: TrainingEventORM) -> TrainingEvent:
        return TrainingEvent(
            job_id=row.job_id,
            ts=row.ts,
            level=row.level,
            message=row.message,
            payload=row.payload,
        )

    @staticmethod
    def _artifact_to_domain(row: ArtifactORM) -> ArtifactRef:
        return ArtifactRef(
            id=row.id,
            uri=row.uri,
            kind=row.kind,
            metadata=row.metadata_json,
            name=row.name,
            file_size=row.file_size,
            file_hash=row.file_hash,
            format=row.format,
            created_at=row.created_at,
        )
